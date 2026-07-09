#!/usr/bin/env python3
"""
搜索采集自动化脚本（v2：CDP Input 人类翻页 + 多语言 + 0结果告警）

通过 CDP Proxy 在 Google/Bing/Baidu 上采集搜索结果 URL：
  - 三引擎并行（TabPool 内）
  - 人类翻页（CDP Input，isTrusted=true，非 JS click）
  - 多语言环境（Emulation locale/UA）
  - 0 结果告警（防选择器失效静默失败）
去重过滤后输出 clean URL 文件和执行报告。

用法：
  python serp_collect.py \
    --search-words urls/round-1/search-words.txt \
    --output-dir urls/round-1 \
    [--cdp-proxy http://localhost:3456] \
    [--locale zh-CN] \
    [--min-urls 50] \
    [--max-pages 6]
"""

import argparse
import io
import json
import os
import re
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_client import CdpClient
from human_behavior import HumanBehavior, poisson_sleep
from locale_service import apply_locale

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ENGINES = ['google', 'bing', 'baidu']
MAX_PAGES_PER_ENGINE = 6
PAGINATION_SELECTORS = {
    'google': '#pnnext',
    'bing': 'a.sb_pagN',
    'baidu': 'a.n:last-child',
}


def load_serp_script():
    """加载 serp_extract.js 并包装为 eval 注入脚本。"""
    path = os.path.join(SCRIPT_DIR, 'serp_extract.js')
    with open(path, 'r', encoding='utf-8') as f:
        src = f.read()
    return f"(function() {{\n{src}\nreturn JSON.stringify(extractFullSerp());\n}})()"


def build_search_url(engine, query, page=0):
    """构造搜索引擎 URL（原 proxy /search 逻辑，移到采集层）。"""
    q = quote(query)
    if engine == 'bing':
        return f'https://www.bing.com/search?q={q}&first={page * 10 + 1}'
    if engine == 'baidu':
        return f'https://www.baidu.com/s?wd={q}&pn={page * 10}'
    return f'https://www.google.com/search?q={q}' + (f'&start={page * 10}' if page else '')


def extract_serp(client, target_id, serp_script):
    """注入 serp_extract.js 提取当前搜索页 URL。"""
    val, err = client.eval(target_id, serp_script)
    if err or val is None:
        return None
    if isinstance(val, str):
        try:
            return json.loads(val)
        except json.JSONDecodeError:
            return None
    if isinstance(val, dict):
        return val
    return None


def wait_for_page(client, target_id, timeout=8):
    """翻页后等待页面加载完成。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        val, _ = client.eval(target_id, 'document.readyState')
        if val == 'complete':
            return True
        time.sleep(0.2)
    return False


def click_next_page(human, client, target_id, engine, next_url=None):
    """翻页：优先 navigate(URL)（后台 tab 稳定，不依赖 Input 事件，绕过节流超时）；
    click_selector 仅作 fallback 且 try 包（后台 tab Input 节流会超时，不再中断采集）。"""
    if next_url:
        try:
            client.navigate(target_id, next_url)
            return True
        except Exception:
            pass  # navigate 失败再试 click
    selector = PAGINATION_SELECTORS.get(engine)
    if selector:
        try:
            ok, _ = human.click_selector(target_id, selector)
            if ok:
                return True
        except Exception:
            pass  # 后台 tab Input 节流致超时，放弃本页翻页
    return False


def collect_engine(client, human, keyword, engine, max_pages, serp_script, locale=None):
    """单引擎采集：人类翻页，逐页提取 URL。返回 (urls, pages, error, zero_results)。"""
    urls = []
    pages_done = 0
    error = None
    zero_results = False

    try:
        with client.acquire_tab(build_search_url(engine, keyword)) as tid:
            if locale:
                try:
                    apply_locale(client, tid, locale)
                except Exception:
                    pass

            for page in range(max_pages):
                # v2: 人类滚动（协议级 + 分段随机），触发懒加载
                try:
                    human.human_scroll(tid, 'down', 2000)
                except Exception:
                    pass

                serp = extract_serp(client, tid, serp_script)
                if not serp:
                    error = f'Extraction failed at page {page}'
                    break
                if serp.get('error'):
                    error = serp['error']
                    break

                page_urls = serp.get('urls', [])
                # v2: 0 结果告警——首页 0 结果通常意味着选择器失效或被反爬
                if page == 0 and len(page_urls) == 0:
                    zero_results = True
                urls.extend(page_urls)
                pages_done += 1

                pagination = serp.get('pagination', {})
                if not pagination.get('hasNext', False) or page >= max_pages - 1:
                    break

                ok = click_next_page(human, client, tid, engine, pagination.get('nextUrl'))
                if not ok:
                    break
                wait_for_page(client, tid)
                poisson_sleep(1.0)  # v2: 翻页后人类节奏
    except Exception as e:
        error = f'{type(e).__name__}: {str(e)[:80]}'

    return urls, pages_done, error, zero_results


def collect_keyword(client, human, keyword, max_pages, serp_script, locale=None, workdir=None):
    """单关键词跨三引擎并行采集 + 跨引擎去重。"""
    all_urls = []
    engine_reports = []

    def fetch_engine(engine):
        urls, pages, err, zero = collect_engine(client, human, keyword, engine, max_pages, serp_script, locale)
        return engine, urls, pages, err, zero

    with ThreadPoolExecutor(max_workers=len(ENGINES)) as executor:
        futures = {executor.submit(fetch_engine, e): e for e in ENGINES}
        for future in as_completed(futures):
            engine, urls, pages, err, zero = future.result()
            engine_reports.append({
                'engine': engine,
                'pages': pages,
                'urls': len(urls),
                'error': err,
                'zero_results': zero,
            })
            all_urls.extend(urls)
            if zero:
                # 领域事件 + 显式告警（防选择器失效静默失败）
                if workdir:
                    try:
                        from events import emit
                        emit(workdir, 'ZERO_RESULTS', {'engine': engine, 'keyword': keyword})
                    except Exception:
                        pass
                print(f"  [!] {engine} 首页 0 结果——选择器可能失效或被反爬拦截", file=sys.stderr)

    # 跨引擎去重
    seen = set()
    unique = []
    for u in all_urls:
        if u not in seen:
            seen.add(u)
            unique.append(u)

    engine_order = {e: i for i, e in enumerate(ENGINES)}
    engine_reports.sort(key=lambda r: engine_order.get(r['engine'], 99))

    return unique, engine_reports


def run_dedup(raw_file, clean_file):
    """调 url_dedup.py 去重。"""
    dedup_script = os.path.join(SCRIPT_DIR, 'url_dedup.py')
    cmd = [sys.executable, dedup_script, raw_file, '-o', clean_file]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=30)
        return True
    except subprocess.CalledProcessError as e:
        print(f"  url_dedup error: {e.stderr}", file=sys.stderr)
        return False


def safe_name(keyword):
    """关键词转安全文件名。"""
    return re.sub(r'[^\w\s-]', '', keyword).strip().replace(' ', '-')[:60]


def write_report(results, min_urls, output_dir):
    """写 _report.md。"""
    lines = [
        "# 搜索采集报告（v2 人类翻页）\n",
        "## 汇总\n",
        f"- 搜索方向: {len(results)} 个",
        f"- 达标: {sum(1 for r in results if r['clean_count'] >= min_urls)} 个",
        f"- 不足: {sum(1 for r in results if r['clean_count'] < min_urls)} 个",
        f"- 有效 URL 总数: {sum(r['clean_count'] for r in results)}",
        "",
    ]

    for r in results:
        status = "[OK]" if r['clean_count'] >= min_urls else "[LOW]"
        lines.append(f"## {r['keyword']}\n")
        lines.append(f"- 状态: {status} ({r['clean_count']}/{min_urls})")
        lines.append(f"- 原始: {r['raw_count']}  有效: {r['clean_count']}")
        for er in r['engine_reports']:
            flags = ""
            if er.get('zero_results'):
                flags += " [0结果!]"
            err = f" [!] {er['error']}" if er.get('error') else ""
            lines.append(f"  - {er['engine']}: {er['pages']}p {er['urls']}u{flags}{err}")
        lines.append("")

    path = os.path.join(output_dir, '_report.md')
    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))


def main():
    parser = argparse.ArgumentParser(description='搜索采集自动化脚本（v2）')
    parser.add_argument('--search-words', required=True, help='搜索词列表文件')
    parser.add_argument('--output-dir', required=True, help='输出目录')
    parser.add_argument('--cdp-proxy', default='http://localhost:3456', help='CDP Proxy 地址')
    parser.add_argument('--locale', default='zh-CN', help='采集语言环境（zh-CN/en-US/ja-JP/...）')
    parser.add_argument('--min-urls', type=int, default=50, help='最低 URL 数')
    parser.add_argument('--max-pages', type=int, default=MAX_PAGES_PER_ENGINE, help='每引擎最大页数')
    parser.add_argument('--workdir', default=None, help='研究工作目录（传入则写 _events.log；不传则仅 stderr 告警）')
    args = parser.parse_args()

    # v2: 用 cdp_client 检查连通性
    client = CdpClient(proxy=args.cdp_proxy, tab_pool_size=30)
    if not client.is_ready():
        print(f"CDP Proxy/Chrome 不可用: {args.cdp_proxy}", file=sys.stderr)
        sys.exit(1)
    h = client.health() or {}
    print(f"CDP Proxy 已连接，当前 {h.get('tabCount', '?')} 个 tab（locale={args.locale}）")

    human = HumanBehavior(client)

    with open(args.search_words, 'r', encoding='utf-8') as f:
        keywords = [l.strip() for l in f if l.strip()]
    print(f"共 {len(keywords)} 个搜索方向")

    serp_script = load_serp_script()
    os.makedirs(args.output_dir, exist_ok=True)

    results = []
    total_start = time.time()
    for i, kw in enumerate(keywords, 1):
        kw_start = time.time()
        print(f"\n[{i}/{len(keywords)}] {kw}")

        urls, engine_reports = collect_keyword(
            client, human, kw, args.max_pages, serp_script, args.locale, args.workdir
        )
        kw_elapsed = time.time() - kw_start
        print(f"  采集: {len(urls)} URL ({kw_elapsed:.0f}s)")

        sname = safe_name(kw)
        raw_path = os.path.join(args.output_dir, f"{sname}.raw.txt")
        with open(raw_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(urls) + '\n')

        clean_path = os.path.join(args.output_dir, f"{sname}.clean.txt")
        dedup_ok = run_dedup(raw_path, clean_path)

        clean_count = 0
        if dedup_ok and os.path.exists(clean_path):
            with open(clean_path, 'r', encoding='utf-8') as f:
                clean_count = len([l for l in f if l.strip()])

        mark = '[OK]' if clean_count >= args.min_urls else '[LOW]'
        print(f"  {mark} valid: {clean_count}/{args.min_urls}")

        results.append({
            'keyword': kw,
            'raw_count': len(urls),
            'clean_count': clean_count,
            'engine_reports': engine_reports,
        })

    write_report(results, args.min_urls, args.output_dir)

    total_elapsed = time.time() - total_start
    ok = sum(1 for r in results if r['clean_count'] >= args.min_urls)
    print(f"\n完成: {ok}/{len(results)} 达标, 总耗时 {total_elapsed:.0f}s")


if __name__ == '__main__':
    main()
