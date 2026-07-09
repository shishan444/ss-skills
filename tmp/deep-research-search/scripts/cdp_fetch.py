import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

"""
CDP Proxy 兜底获取工具（v2：并发 + 人类交互）

功能：
  - 读取 url_fetch.py 产出的 _failed_urls.txt 中的 CDP 候选
  - 通过 CDP Proxy 并发获取（tab池内，默认并发 5-8）
  - 人类交互：点击展开/加载更多 + 滚动触发懒加载；浏览器登录态解决 403 反爬
  - 产出格式与 url_fetch.py 一致，下游消化流程无需区分来源

用法：
  python cdp_fetch.py <workdir> [--round N] [--cdp-proxy URL] [--max N] [--concurrency N]

输出：
  data/round-N/{direction}-{seq}.md  — 补获取的页面内容
  data/round-N/_cdp_report.md        — CDP 兜底执行报告
"""

import argparse
import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_client import CdpClient
from human_behavior import HumanBehavior, poisson_sleep
from storage import record_url

CDP_PROXY_DEFAULT = 'http://localhost:3456'
PAGE_LOAD_WAIT = 4  # 页面加载等待秒数

# DOM 提取 JS（不依赖外部 CDN，纯浏览器原生 API）
EXTRACT_JS = r'''
(function() {
  try {
    var title = document.title || '';
    var selectors = [
      'article',
      '[role="article"]',
      'main',
      '.Post-RichTextContainer',
      '.RichText',
      '.article-content',
      '.article-body',
      '.syl-article',
      '.post-body',
      '.entry-content',
      '.content-body',
      '.story-body',
      '#article-content',
      '#content',
      '.content',
    ];
    var el = null;
    for (var i = 0; i < selectors.length; i++) {
      var candidate = document.querySelector(selectors[i]);
      if (candidate && candidate.innerText.trim().length > 200) {
        el = candidate;
        break;
      }
    }
    if (!el) {
      var bodyText = document.body ? document.body.innerText.trim() : '';
      if (bodyText.length < 200) {
        return JSON.stringify({success: false, error: '页面内容过短', title: title, length: bodyText.length});
      }
      return JSON.stringify({success: true, title: title, content: bodyText, length: bodyText.length, source: 'body'});
    }
    var text = el.innerText.replace(/\n{3,}/g, '\n\n').trim();
    if (text.length < 100) {
      return JSON.stringify({success: false, error: '提取内容过短', title: title, length: text.length});
    }
    return JSON.stringify({success: true, title: title, content: text, length: text.length, source: 'article'});
  } catch(e) {
    return JSON.stringify({success: false, error: e.message, title: document.title || ''});
  }
})()
'''

# 内容交互：常见"展开/加载更多"按钮（安全选择器，点到第一个即止）
INTERACT_SELECTORS = [
    'button.show-more', 'button.load-more', 'a.load-more',
    '.show-full', '.read-all', '.btn-expand',
    '[aria-label*="展开"]', '[aria-label*="全文"]',
]


def interact_for_content(human, target_id):
    """人类交互：滚动触发懒加载 + 尝试点常见展开按钮。任何异常都不阻塞主流程。"""
    try:
        human.human_scroll(target_id, 'down', 2000)
    except Exception:
        pass
    for sel in INTERACT_SELECTORS:
        try:
            ok, _ = human.click_selector(target_id, sel)
            if ok:
                poisson_sleep(1.5)
                break  # 只点第一个匹配的，避免误点
        except Exception:
            continue


def cdp_fetch_url(client, human, url, wait=PAGE_LOAD_WAIT, interact=True):
    """用 CDP client 获取单个 URL：开 tab → 等载 → 交互 → 提取 → 关 tab（租约自动）。"""
    result = {
        'url': url, 'success': False, 'title': '', 'text': '',
        'quality': None, 'error': None, 'source': 'cdp_proxy',
    }
    try:
        with client.acquire_tab(url) as tid:
            time.sleep(wait)
            if interact:
                interact_for_content(human, tid)
            raw, err = client.eval(tid, EXTRACT_JS)
            if err:
                result['error'] = f'CDP eval 失败: {err}'
                return result
            if not raw:
                result['error'] = 'CDP eval 返回空'
                return result
            extract = json.loads(raw)
            if not extract.get('success'):
                result['error'] = extract.get('error', '提取失败')
                result['title'] = extract.get('title', '')
                return result
            result['title'] = extract.get('title', '')
            result['text'] = extract.get('content', '')
            result['success'] = True
            # 不做质量/相关性判断（交给识别层 LLM）
    except Exception as e:
        result['error'] = f'{type(e).__name__}: {str(e)[:100]}'
    return result


def format_output(result, direction, seq):
    """与 url_fetch.py 一致的输出格式。"""
    from urllib.parse import urlparse
    domain = urlparse(result['url']).netloc.replace('www.', '')
    length = len(result.get('text', ''))
    lines = [
        f"URL: {result['url']}",
        f"搜索方向: {direction}",
        f"工具: url_fetch ({result.get('source', 'cdp_proxy')})",
        f"来源域名: {domain} | 正文长度: {length}",
        f"标题: {result['title']}",
        "",
    ]
    if result['success']:
        lines.append(f"# {result['title']}")
        lines.append("")
        lines.append(result['text'])
    else:
        lines.append("# 获取失败")
        lines.append("")
        lines.append(f"错误: {result['error']}")
    return '\n'.join(lines)


def find_existing_count(data_dir, prefix):
    """查找已有的最大序号，从 url_fetch.py 产出之后接续编号。"""
    if not os.path.exists(data_dir):
        return 0
    max_seq = 0
    for f in os.listdir(data_dir):
        if f.startswith(prefix) and f.endswith('.md') and not f.startswith('_'):
            match = re.search(r'-(\d+)\.md$', f)
            if match:
                seq = int(match.group(1))
                if seq > max_seq:
                    max_seq = seq
    return max_seq


def load_failed_urls(failed_path):
    """读取 _failed_urls.txt，返回 CDP 候选列表。"""
    candidates = []
    cdp_error_classes = {'anticrawl', 'extract_failed', 'retryable'}
    with open(failed_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            parts = line.split('\t')
            if len(parts) < 4:
                continue
            url, direction, error, error_class = parts[0], parts[1], parts[2], parts[3]
            if error_class in cdp_error_classes:
                candidates.append({
                    'url': url, 'direction': direction,
                    'error': error, 'error_class': error_class,
                })
    return candidates


def main():
    parser = argparse.ArgumentParser(description='CDP Proxy 兜底获取工具（v2 并发 + 人类交互）')
    parser.add_argument('workdir', help='工作目录路径')
    parser.add_argument('--round', '-r', type=int, required=True, help='轮次编号')
    parser.add_argument('--cdp-proxy', '-p', default=CDP_PROXY_DEFAULT, help='CDP Proxy 地址')
    parser.add_argument('--max', '-m', type=int, default=20, help='最多处理 URL 数')
    parser.add_argument('--concurrency', '-c', type=int, default=5, help='并发数（tab池内，建议 5-8）')
    parser.add_argument('--wait', '-w', type=float, default=PAGE_LOAD_WAIT, help='页面加载等待秒数')
    parser.add_argument('--no-interact', action='store_true', help='禁用人类交互（展开/滚动）')
    args = parser.parse_args()

    round_dir = f'round-{args.round}'
    data_dir = os.path.join(args.workdir, 'data', round_dir)
    failed_path = os.path.join(data_dir, '_failed_urls.txt')

    if not os.path.exists(failed_path):
        print(f"未找到失败 URL 文件: {failed_path}")
        sys.exit(1)

    # v2: 用 cdp_client 检查连通性（含 TabPool 状态）
    client = CdpClient(proxy=args.cdp_proxy, tab_pool_size=30)
    if not client.is_ready():
        print(f"CDP Proxy/Chrome 不可用: {args.cdp_proxy}")
        sys.exit(1)
    h = client.health() or {}
    print(f"CDP Proxy 已连接，当前 {h.get('tabCount', '?')} 个 tab（上限 {h.get('tabPoolLimit', 30)}，并发={args.concurrency}）")

    human = HumanBehavior(client)
    candidates = load_failed_urls(failed_path)
    print(f"CDP 候选 URL: {len(candidates)} 个")

    if not candidates:
        print("无 CDP 候选，退出")
        sys.exit(0)

    candidates = candidates[:args.max]

    # 续编号（并发需加锁）
    lock = threading.Lock()
    dir_counts = {}
    for c in candidates:
        d = c['direction']
        if d not in dir_counts:
            prefix = d.replace(' ', '-')
            dir_counts[d] = find_existing_count(data_dir, prefix)
            print(f"  [{d}] 已有 {dir_counts[d]} 个文件，从 {dir_counts[d]+1} 开始编号")

    stats = {'success': 0, 'failed': 0, 'low_quality': 0}
    results = []
    progress = {'i': 0}

    def worker(c):
        direction = c['direction']
        with lock:
            dir_counts[direction] += 1
            seq = dir_counts[direction]
            progress['i'] += 1
            idx = progress['i']
        print(f"\n[{idx}/{len(candidates)}] {c['error_class']}: {c['url'][:80]}")

        result = cdp_fetch_url(client, human, c['url'], wait=args.wait, interact=not args.no_interact)
        result['url'] = c['url']

        output = format_output(result, direction, seq)
        out_path = os.path.join(data_dir, f"{direction.replace(' ', '-')}-{seq}.md")
        with open(out_path, 'w', encoding='utf-8') as f:
            f.write(output)

        # 记录到 manifest（溯源 + 幂等；失败不阻塞）
        try:
            record_url(args.workdir, c['url'], direction,
                       data_file=out_path, round_n=args.round,
                       source=result.get('source', 'cdp_proxy'),
                       quality=result.get('quality'),
                       status='success' if result['success'] else 'failed')
        except Exception:
            pass

        with lock:
            if result['success']:
                stats['success'] += 1
                print(f"  OK [CDP] [{seq}] {result['title'][:50]} ({len(result['text'])}字)")
            else:
                stats['failed'] += 1
                print(f"  FAIL [{seq}] {result['error'][:60]}")
            results.append({
                'url': c['url'], 'direction': direction, 'error_class': c['error_class'],
                'success': result['success'], 'title': result.get('title', ''),
                'error': result.get('error', ''),
            })

    # 并发获取（TabPool 信号量在 acquire_tab 内控制实际 tab 数）
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        list(executor.map(worker, candidates))

    # 生成报告
    report = [
        f"# 第 {args.round} 轮 CDP 兜底报告（v2 并发）",
        "",
        "## 统计",
        f"- 并发数: {args.concurrency}",
        f"- CDP 候选总数: {len(candidates)}",
        f"- 实际处理: {len(results)}",
        f"- 成功: {stats['success']}",
        f"- 低质量: {stats['low_quality']}",
        f"- 失败: {stats['failed']}",
        f"- 成功率: {stats['success']/max(1,len(results))*100:.1f}%",
        "",
        "## 详细结果",
        "",
    ]
    for r in results:
        tag = 'OK' if r['success'] else 'FAIL'
        report.append(f"- [{tag}] [{r['error_class']}] {r['title'][:50]} — {r['url'][:80]}")
        if r['error']:
            report.append(f"  错误: {r['error']}")
    report.append("")

    report_path = os.path.join(data_dir, '_cdp_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report))

    # 领域事件：兜底完成（写入 _events.log，供可观测）
    try:
        from events import emit
        emit(args.workdir, 'FETCH_COMPLETED', {
            'round': args.round, 'candidates': len(candidates),
            'success': stats['success'], 'failed': stats['failed'],
        })
    except Exception:
        pass

    print(f"\n{'='*50}")
    print(f"CDP 兜底完成: 成功 {stats['success']}, 低质量 {stats['low_quality']}, 失败 {stats['failed']}")
    print(f"报告: {report_path}")


if __name__ == '__main__':
    main()
