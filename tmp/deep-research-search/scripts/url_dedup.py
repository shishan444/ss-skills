"""
URL 去重与清洗脚本

功能：
  1. URL 标准化（去除追踪参数、统一格式）
  2. 按域名+路径去重
  3. 标记疑似广告/低质链接
  4. 输出过滤报告

用法：
  python url_dedup.py <input_file> [--output <output_file>] [--report <report_file>]

输入文件格式：每行一个 URL（纯 URL，无需编号）
输出文件格式：每行一个清洗后的 URL
"""

import argparse
import re
import sys
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

# 常见的广告追踪参数（去除后不影响页面内容）
TRACKING_PARAMS = {
    'utm_source', 'utm_medium', 'utm_campaign', 'utm_term', 'utm_content',
    'fbclid', 'gclid', 'gclsrc', 'dclid', 'msclkid',
    'ref', 'referrer', 'source', 'from', 'share',
    'spm', 'scm', 'nsukey', 'isappinstalled',
    'nsukey', 'pos', 'abtest',
}

# 疑似广告 URL 的路径/参数关键词
AD_INDICATORS = [
    r'/ad[s]?(?:_)?', r'/click\?', r'/track', r'/redirect',
    r'[?&]click_id=', r'[?&]ad_id=', r'[?&]campaign_id=',
    r'/affiliat', r'/sponsor', r'/promo',
]

# 已知低质聚合站域名（可按需扩展）
LOW_QUALITY_DOMAINS = {
    'douyin.com', 'tiktok.com',  # 短视频平台，通常无深度文本内容
}


def normalize_url(url: str) -> str:
    """URL 标准化：去除追踪参数、统一格式"""
    url = url.strip()
    if not url:
        return ''

    # 补全 scheme
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    parsed = urlparse(url)

    # 域名小写
    domain = parsed.netloc.lower()
    # 去除 www.
    if domain.startswith('www.'):
        domain = domain[4:]

    # 路径去除末尾斜杠
    path = parsed.path.rstrip('/') or '/'

    # 去除追踪参数
    params = parse_qs(parsed.query, keep_blank_values=True)
    clean_params = {k: v for k, v in params.items() if k.lower() not in TRACKING_PARAMS}
    query = urlencode(clean_params, doseq=True) if clean_params else ''

    return urlunparse((parsed.scheme, domain, path, parsed.params, query, ''))


def is_likely_ad(url: str) -> tuple[bool, str]:
    """判断 URL 是否疑似广告"""
    url_lower = url.lower()
    for pattern in AD_INDICATORS:
        if re.search(pattern, url_lower):
            return True, f"匹配广告模式: {pattern}"
    return False, ''


def is_low_quality_domain(domain: str) -> bool:
    """判断域名是否属于低质站点"""
    domain_lower = domain.lower()
    if domain_lower.startswith('www.'):
        domain_lower = domain_lower[4:]
    return domain_lower in LOW_QUALITY_DOMAINS


def extract_domain(normalized_url: str) -> str:
    """从标准化 URL 提取域名"""
    parsed = urlparse(normalized_url)
    return parsed.netloc


def dedup_urls(urls: list[str]) -> dict:
    """
    对 URL 列表执行去重与清洗

    返回:
      {
        'clean': [(url, original_url), ...],       # 去重后的有效 URL
        'duplicates': [(url, original_url), ...],   # 被去重的
        'ads': [(url, reason), ...],                # 疑似广告
        'low_quality': [(url, domain), ...],        # 低质域名
        'stats': { ... }                            # 统计信息
      }
    """
    seen_keys = {}  # domain+path -> first_url
    clean = []
    duplicates = []
    ads = []
    low_quality = []

    for original_url in urls:
        original_url = original_url.strip()
        if not original_url or original_url.startswith('#'):
            continue

        normalized = normalize_url(original_url)
        if not normalized:
            continue

        # 检查广告
        is_ad, ad_reason = is_likely_ad(normalized)
        if is_ad:
            ads.append((normalized, ad_reason))
            continue

        # 检查域名质量
        domain = extract_domain(normalized)
        if is_low_quality_domain(domain):
            low_quality.append((normalized, domain))
            continue

        # 去重键：完整标准化URL（含查询参数，因normalize已移除追踪参数）
        dedup_key = normalized

        if dedup_key in seen_keys:
            duplicates.append((normalized, seen_keys[dedup_key]))
        else:
            seen_keys[dedup_key] = normalized
            clean.append((normalized, original_url))

    return {
        'clean': clean,
        'duplicates': duplicates,
        'ads': ads,
        'low_quality': low_quality,
        'stats': {
            'input_count': len(urls),
            'clean_count': len(clean),
            'duplicates_removed': len(duplicates),
            'ads_removed': len(ads),
            'low_quality_removed': len(low_quality),
        }
    }


def generate_report(result: dict) -> str:
    """生成文本格式过滤报告"""
    stats = result['stats']
    lines = [
        "# URL 去重与过滤报告",
        "",
        f"## 统计",
        f"- 输入 URL 总数: {stats['input_count']}",
        f"- 有效 URL: {stats['clean_count']}",
        f"- 去重移除: {stats['duplicates_removed']}",
        f"- 广告移除: {stats['ads_removed']}",
        f"- 低质域名移除: {stats['low_quality_removed']}",
        f"- 过滤率: {(1 - stats['clean_count'] / max(stats['input_count'], 1)) * 100:.1f}%",
        "",
    ]

    if result['ads']:
        lines.append("## 疑似广告链接")
        for url, reason in result['ads']:
            lines.append(f"- {reason}: {url}")
        lines.append("")

    if result['low_quality']:
        lines.append("## 低质域名")
        for url, domain in result['low_quality']:
            lines.append(f"- {domain}: {url}")
        lines.append("")

    if result['duplicates']:
        lines.append("## 重复链接（示例，最多显示20条）")
        for url, original in result['duplicates'][:20]:
            lines.append(f"- 重复: {url}")
            lines.append(f"  保留: {original}")
        if len(result['duplicates']) > 20:
            lines.append(f"- ... 共 {len(result['duplicates'])} 条重复")
        lines.append("")

    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description='URL 去重与清洗')
    parser.add_argument('input_file', help='输入文件（每行一个URL）')
    parser.add_argument('--output', '-o', default=None, help='输出文件路径（默认 stdout）')
    parser.add_argument('--report', '-r', default=None, help='过滤报告输出路径')
    args = parser.parse_args()

    with open(args.input_file, 'r', encoding='utf-8') as f:
        urls = f.readlines()

    result = dedup_urls(urls)

    # 输出清洗后的 URL 列表
    output_lines = [url for url, _ in result['clean']]
    output_text = '\n'.join(output_lines)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(output_text + '\n')
        print(f"已写入 {len(output_lines)} 个有效URL到 {args.output}")
    else:
        print(output_text)

    # 输出报告
    report = generate_report(result)
    if args.report:
        with open(args.report, 'w', encoding='utf-8') as f:
            f.write(report)
        print(f"过滤报告已写入 {args.report}")
    else:
        print("\n" + report, file=sys.stderr)


if __name__ == '__main__':
    main()
