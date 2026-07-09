import io
import sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

"""
批量 URL 内容获取工具

功能：
  - 从 urls/round-N/*.clean.txt 读取 URL 列表
  - requests 下载 + trafilatura/BS4 两级提取
  - HTTP 状态码分类（重试/CDP候选/跳过）
  - 并发请求，质量评分
  - 断点续传，生成获取报告

用法：
  python url_fetch.py <workdir> [--round N] [--max-per-dir N] [--concurrency N]

输出：
  data/round-N/{direction}-{seq}.md  — 获取的页面内容
  data/round-N/_report.md            — 获取报告
  data/round-N/_failed_urls.txt      — 失败 URL 列表（供 CDP 兜底）
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse

import requests
import trafilatura

# 质量评分（单一来源，与 cdp_fetch.py 共用，避免双份漂移）
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from storage import record_url

try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

# 请求头伪装
HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) '
        'Chrome/131.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    'Accept-Encoding': 'gzip, deflate',
    'Connection': 'keep-alive',
}

# 可重试的 HTTP 状态码
RETRYABLE_STATUS = {429, 502, 503, 504}
# 反爬/需认证 → CDP 候选
ANTICRAWL_STATUS = {403, 401}
# 永久失败
PERMANENT_FAIL_STATUS = {400, 404, 410, 451}

# 不可能提取文本的域名
SKIP_DOMAINS = {
    'youtube.com', 'youtu.be', 'vimeo.com', 'bilibili.com',
    'douyin.com', 'tiktok.com', 'dailymotion.com',
    'google.com', 'bing.com', 'baidu.com', 'duckduckgo.com',
}

# 二进制文件扩展名
BINARY_EXTS = {
    '.pdf', '.doc', '.docx', '.ppt', '.pptx', '.xls', '.xlsx',
    '.zip', '.rar', '.gz', '.tar', '.7z', '.exe', '.dmg',
    '.mp3', '.mp4', '.avi', '.mov', '.wmv', '.flv', '.mkv',
    '.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.webp',
    '.ico', '.woff', '.woff2', '.ttf', '.eot',
}

MAX_RETRIES = 2


# quality_score 已移至 quality.py（见上方 import）

def classify_url(url: str) -> str | None:
    """预分类 URL，返回跳过原因或 None（需要获取）。"""
    parsed = urlparse(url)
    path = parsed.path.lower()
    domain = parsed.netloc.lower()

    # 去除 www.
    domain_bare = domain[4:] if domain.startswith('www.') else domain

    # 二进制文件
    if any(path.endswith(ext) for ext in BINARY_EXTS):
        return '二进制文件'

    # 视频网站 / 搜索引擎页面
    if domain_bare in SKIP_DOMAINS or any(
        d in domain_bare for d in ['.youtube.com', '.bilibili.com']
    ):
        # google.com/search 是搜索页，不是内容页
        if 'google.com' in domain_bare and '/search' in path:
            return '搜索引擎页面'
        if domain_bare in SKIP_DOMAINS:
            return '视频/搜索平台'

    return None


def bs4_fallback_extract(html: str) -> str | None:
    """BeautifulSoup 降级提取：去除噪声后提取正文文本。"""
    if not HAS_BS4 or not html:
        return None

    soup = BeautifulSoup(html, 'html.parser')

    # 移除噪声元素
    for tag in soup.find_all([
        'nav', 'header', 'footer', 'aside', 'script', 'style',
        'noscript', 'iframe', 'form', 'svg',
    ]):
        tag.decompose()
    for tag in soup.find_all(class_=re.compile(
        r'nav|menu|sidebar|comment|ad|banner|footer|header|social|share|related|recommend'
    )):
        tag.decompose()
    for tag in soup.find_all(id=re.compile(
        r'nav|menu|sidebar|comment|ad|footer|header'
    )):
        tag.decompose()

    # 优先提取 article/main
    content_area = (
        soup.find('article')
        or soup.find('main')
        or soup.find(role='article')
        or soup.find(class_=re.compile(r'article|post|content|entry|body'))
    )
    if not content_area:
        content_area = soup.find('body') or soup

    text = content_area.get_text(separator='\n', strip=True)

    # 清理空行
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    clean_text = '\n'.join(lines)

    if len(clean_text) < 100:
        return None

    return clean_text


def download_html(url: str, timeout: int = 20) -> dict:
    """用 requests 下载 HTML，返回分类后的结果。

    返回:
      {'html': str, 'status': int, 'error': str|None, 'error_class': str}
      error_class: None | 'retryable' | 'anticrawl' | 'permanent' | 'network'
    """
    result = {
        'html': None,
        'status': None,
 'error': None,
        'error_class': None,
    }

    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url,
                headers=HEADERS,
                timeout=(10, timeout),
                allow_redirects=True,
            )
            result['status'] = resp.status_code

            if resp.status_code == 200:
                # 检查 content-type
                ct = resp.headers.get('Content-Type', '')
                if 'text/html' not in ct and 'application/xhtml' not in ct:
                    # 可能是 JSON API / 图片等
                    result['error'] = f'非HTML内容: {ct[:60]}'
                    result['error_class'] = 'permanent'
                    return result
                result['html'] = resp.text
                return result

            if resp.status_code in RETRYABLE_STATUS:
                if attempt < MAX_RETRIES:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                result['error'] = f'HTTP {resp.status_code} (重试耗尽)'
                result['error_class'] = 'retryable'
                return result

            if resp.status_code in ANTICRAWL_STATUS:
                result['error'] = f'HTTP {resp.status_code} (反爬/需认证)'
                result['error_class'] = 'anticrawl'
                return result

            if resp.status_code in PERMANENT_FAIL_STATUS:
                result['error'] = f'HTTP {resp.status_code}'
                result['error_class'] = 'permanent'
                return result

            # 其他状态码
            result['error'] = f'HTTP {resp.status_code}'
            result['error_class'] = 'permanent'
            return result

        except requests.exceptions.Timeout:
            if attempt < MAX_RETRIES:
                continue
            result['error'] = '请求超时'
            result['error_class'] = 'network'
            return result

        except requests.exceptions.ConnectionError as e:
            if attempt < MAX_RETRIES:
                time.sleep(1)
                continue
            result['error'] = f'连接失败: {str(e)[:80]}'
            result['error_class'] = 'network'
            return result

        except requests.exceptions.RequestException as e:
            result['error'] = f'请求异常: {type(e).__name__}'
            result['error_class'] = 'network'
            return result

    return result


def extract_title(html: str) -> str:
    """从 HTML 中提取标题。"""
    match = re.search(r'<title[^>]*>([^<]+)</title>', html[:5000], re.IGNORECASE)
    if match:
        title = match.group(1).strip()
        # 清理常见后缀
        for suffix in [' - ', ' _ ', ' | ', ' — ']:
            if suffix in title:
                parts = title.split(suffix)
                title = parts[0].strip()
                break
        return title[:200]
    return ''


def fetch_url(url: str, timeout: int = 20) -> dict:
    """获取单个 URL 内容，三级处理：下载 → trafilatura提取 → BS4降级。"""
    result = {
        'url': url,
        'success': False,
        'title': '',
        'text': '',
        'quality': None,
        'error': None,
        'source': '',
        'error_class': None,
    }

    # 预分类
    skip_reason = classify_url(url)
    if skip_reason:
        result['error'] = skip_reason
        result['source'] = 'skipped'
        return result

    # 下载
    dl = download_html(url, timeout=timeout)
    result['error_class'] = dl['error_class']

    if dl['html'] is None:
        result['error'] = dl['error']
        result['source'] = 'download_failed'
        return result

    html = dl['html']
    title = extract_title(html)

    # Level 1: trafilatura 提取
    text = trafilatura.extract(
        html,
        include_links=False,
        include_tables=True,
        include_formatting=True,
        favor_precision=True,  # 实测：噪声页(帮助/JS拦截)返回空→丢弃；正文+页脚噪声→去页脚留正文；英文源无损
    )

    extractor_used = 'trafilatura'

    # Level 2: BS4 降级
    if not text or len(text.strip()) < 100:
        bs4_text = bs4_fallback_extract(html)
        if bs4_text and len(bs4_text) > len(text or ''):
            text = bs4_text
            extractor_used = 'bs4_fallback'

    if not text or len(text.strip()) < 50:
        result['error'] = '内容提取失败（trafilatura+BS4均无法提取）'
        result['title'] = title
        result['source'] = 'extract_failed'
        return result

    result['title'] = title
    result['text'] = text
    result['success'] = True
    result['source'] = extractor_used
    # 不做质量/相关性判断（交给识别层 LLM）；只记客观元信息供其参考

    return result


def format_output(result: dict, direction: str, seq: int) -> str:
    from urllib.parse import urlparse
    domain = urlparse(result['url']).netloc.replace('www.', '')
    length = len(result.get('text', ''))
    lines = [
        f"URL: {result['url']}",
        f"搜索方向: {direction}",
        f"工具: url_fetch ({result.get('source', 'unknown')})",
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


def find_existing_count(data_dir: str, direction: str) -> int:
    if not os.path.exists(data_dir):
        return 0
    prefix = direction.replace(' ', '-')
    max_seq = 0
    for f in os.listdir(data_dir):
        if f.startswith(prefix) and f.endswith('.md') and not f.startswith('_'):
            match = re.search(r'-(\d+)\.md$', f)
            if match:
                seq = int(match.group(1))
                if seq > max_seq:
                    max_seq = seq
    return max_seq


def find_existing_urls(data_dir: str) -> set:
    existing = set()
    if not os.path.exists(data_dir):
        return existing
    for f in os.listdir(data_dir):
        if not f.endswith('.md') or f.startswith('_'):
            continue
        filepath = os.path.join(data_dir, f)
        try:
            with open(filepath, 'r', encoding='utf-8') as fh:
                first_line = fh.readline().strip()
                if first_line.startswith('URL: '):
                    existing.add(first_line[5:])
        except Exception:
            pass
    return existing


def save_result(result: dict, direction: str, seq: int, data_dir: str, prefix: str):
    output = format_output(result, direction, seq)
    out_path = os.path.join(data_dir, f"{prefix}-{seq}.md")
    with open(out_path, 'w', encoding='utf-8') as f:
        f.write(output)


def main():
    parser = argparse.ArgumentParser(description='批量 URL 内容获取工具')
    parser.add_argument('workdir', help='工作目录路径')
    parser.add_argument('--round', '-r', type=int, default=1, help='轮次编号')
    parser.add_argument('--max-per-dir', '-m', type=int, default=15, help='每个方向最大获取数')
    parser.add_argument('--min-score', '-s', type=int, default=30, help='最低质量分')
    parser.add_argument('--concurrency', '-c', type=int, default=5, help='并发数')
    parser.add_argument('--timeout', '-t', type=int, default=20, help='单个 URL 超时（秒）')
    parser.add_argument('--delay', '-d', type=float, default=0.3, help='请求间隔（秒）')
    parser.add_argument('--retries', type=int, default=2, help='可重试错误的最大重试次数')

    args = parser.parse_args()
    global MAX_RETRIES
    MAX_RETRIES = args.retries

    round_dir = f'round-{args.round}'
    urls_dir = os.path.join(args.workdir, 'urls', round_dir)
    data_dir = os.path.join(args.workdir, 'data', round_dir)
    os.makedirs(data_dir, exist_ok=True)

    clean_files = sorted([f for f in os.listdir(urls_dir) if f.endswith('.clean.txt')])
    if not clean_files:
        print(f"未找到 URL 文件: {urls_dir}/*.clean.txt")
        sys.exit(1)

    existing_urls = find_existing_urls(data_dir)
    print(f"已获取: {len(existing_urls)} 个页面（将跳过）")

    stats = {
        'total_urls': 0,
        'skipped_existing': 0,
        'skipped_binary': 0,
        'skipped_platform': 0,
        'fetched': 0,
        'success': 0,
        'low_quality': 0,
        'failed': 0,
        'bs4_fallback': 0,
        'retry_success': 0,
        'anticrawl': 0,
        'network_error': 0,
    }
    failed_urls = []       # (url, direction, error, error_class)
    low_quality_urls = []  # (url, score, reason)

    for clean_file in clean_files:
        direction = clean_file.replace('.clean.txt', '').replace('.txt', '')
        prefix = direction.replace(' ', '-')

        filepath = os.path.join(urls_dir, clean_file)
        with open(filepath, 'r', encoding='utf-8') as f:
            urls = [line.strip() for line in f if line.strip()]

        stats['total_urls'] += len(urls)

        # 过滤已获取的、二进制的、不可提取的
        start_seq = find_existing_count(data_dir, prefix) + 1
        pending = []
        for url in urls:
            if url in existing_urls:
                stats['skipped_existing'] += 1
                continue
            skip_reason = classify_url(url)
            if skip_reason == '二进制文件':
                stats['skipped_binary'] += 1
                failed_urls.append((url, direction, skip_reason, 'binary'))
                continue
            if skip_reason:
                stats['skipped_platform'] += 1
                failed_urls.append((url, direction, skip_reason, 'platform'))
                continue
            pending.append(url)

        pending = pending[:args.max_per_dir]

        if not pending:
            print(f"[{direction}] 无新 URL 需获取")
            continue

        print(f"[{direction}] 获取 {len(pending)}/{len(urls)} 个 URL (并发={args.concurrency})...")

        # 并发获取
        seq_counter = start_seq
        with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
            future_map = {}
            for url in pending:
                future = executor.submit(fetch_url, url, timeout=args.timeout)
                future_map[future] = url

            for future in as_completed(future_map):
                url = future_map[future]
                seq = seq_counter
                seq_counter += 1

                try:
                    result = future.result()
                except Exception as e:
                    result = {
                        'url': url,
                        'success': False,
                        'error': f'线程异常: {type(e).__name__}',
                        'source': 'exception',
                    }

                stats['fetched'] += 1

                if result['success']:
                    stats['success'] += 1
                    if result.get('source') == 'bs4_fallback':
                        stats['bs4_fallback'] += 1

                    save_result(result, direction, seq, data_dir, prefix)
                    src = f"[{result.get('source', '?')}]"
                    print(f"  OK {src} [{seq}] {result['title'][:40]} ({len(result.get('text',''))}字)")

                else:
                    stats['failed'] += 1
                    error_class = result.get('error_class') or 'unknown'
                    failed_urls.append((url, direction, result['error'], error_class))

                    # 反爬和提取失败标记为 CDP 候选
                    if error_class == 'anticrawl':
                        stats['anticrawl'] += 1
                    elif error_class == 'network':
                        stats['network_error'] += 1

                    save_result(result, direction, seq, data_dir, prefix)
                    print(f"  FAIL [{seq}] {result['error'][:60]}")

                # 记录到 manifest（溯源 + 幂等重跑不重复计数；失败不阻塞主流程）
                try:
                    record_url(args.workdir, url, direction,
                               data_file=os.path.join(data_dir, f"{prefix}-{seq}.md"),
                               round_n=args.round, source=result.get('source'),
                               quality=result.get('quality'),
                               status='success' if result['success'] else 'failed')
                except Exception:
                    pass

                # 请求间隔（粗粒度，由线程调度实现）
                if args.delay > 0:
                    time.sleep(args.delay)

    # 生成失败 URL 文件（按错误类型分组）
    failed_path = os.path.join(data_dir, '_failed_urls.txt')
    with open(failed_path, 'w', encoding='utf-8') as f:
        f.write("# 格式: URL\\t方向\\t错误\\t错误分类\\n")
        for url, direction, error, error_class in failed_urls:
            f.write(f"{url}\t{direction}\t{error}\t{error_class}\n")

    # 按错误分类的 CDP 候选（排除二进制和平台）
    cdp_candidates = [
        (url, direction, error)
        for url, direction, error, ec in failed_urls
        if ec in ('anticrawl', 'extract_failed', 'retryable')
    ]

    # 生成报告
    report_lines = [
        f"# 第 {args.round} 轮获取报告",
        "",
        "## 统计",
        f"- URL 总数: {stats['total_urls']}",
        f"- 跳过(已获取): {stats['skipped_existing']}",
        f"- 跳过(二进制): {stats['skipped_binary']}",
        f"- 跳过(视频/搜索平台): {stats['skipped_platform']}",
        f"- 实际请求: {stats['fetched']}",
        f"- 成功: {stats['success']}",
        f"  - trafilatura 提取: {stats['success'] - stats['bs4_fallback']}",
        f"  - BS4 降级提取: {stats['bs4_fallback']}",
        f"- 低质量: {stats['low_quality']}",
        f"- 失败: {stats['failed']}",
        f"  - 反爬/需认证: {stats['anticrawl']}",
        f"  - 网络错误: {stats['network_error']}",
        f"  - 其他: {stats['failed'] - stats['anticrawl'] - stats['network_error']}",
        f"- 成功率: {stats['success']/max(1,stats['fetched'])*100:.1f}%",
        f"- CDP 兜底候选: {len(cdp_candidates)}",
        "",
    ]

    if low_quality_urls:
        report_lines.append("## 低质量 URL")
        report_lines.append("")
        for url, score, reason in low_quality_urls:
            report_lines.append(f"- [{score}分] {reason}: {url[:80]}")
        report_lines.append("")

    if cdp_candidates:
        report_lines.append("## CDP Proxy 兜底候选（反爬/提取失败）")
        report_lines.append("")
        for url, direction, error in cdp_candidates:
            report_lines.append(f"- [{direction}] {error}: {url[:80]}")
        report_lines.append("")

    report_path = os.path.join(data_dir, '_report.md')
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(report_lines))

    print(f"\n{'='*50}")
    print(f"获取完成: 成功 {stats['success']}(BS4降级{stats['bs4_fallback']}), "
          f"失败 {stats['failed']}(反爬{stats['anticrawl']}, 网络{stats['network_error']})")
    print(f"CDP 兜底候选: {len(cdp_candidates)} 个")
    print(f"报告: {report_path}")


if __name__ == '__main__':
    main()
