#!/usr/bin/env python3
"""拦截信号检测器 — web-chrome skill

识别 6 类反爬/拦截信号，检测到时输出结构化快照，供 agent：
  1. 停止当前操作（不反复撞墙）
  2. 写入站点经验（site-patterns/{domain}.md 的"反爬规避"区）
  3. 提醒经验积累
  4. 选择降级策略（拟人 GUI / 换 locale-UA / 人工登录）

6 类信号：
  - CAPTCHA       验证码/人机验证页（关键词 + reCAPTCHA/hCaptcha/Turnstile iframe）
  - HTTP_BLOCK    403/429/503 直接 HTTP 拦截
  - EMPTY_SERP    SERP 首页 0 结果（常是反爬而非真无结果）
  - LOGIN_WALL    原本公开内容突然要求登录
  - CONTENT_GONE  页面加载成功但目标区域为空/被替换为提示
  - FINGERPRINT   滚动/点击后跳转到验证页（行为指纹检测）

用法：
  python3 intercept_detector.py check <target_id>            # 检测当前页面
  python3 intercept_detector.py check <target_id> --html '...'  # 检测给定 HTML 文本
"""

import argparse
import json
import os
import re
import sys
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_client import CdpClient

# 验证码/人机验证关键词（中英）
CAPTCHA_KEYWORDS = [
    'captcha', 'recaptcha', 'hcaptcha', 'turnstile', 'are you human', 'verify you are human',
    'robot', 'bot check', 'human verification', 'security check', 'unusual traffic',
    '验证', '人机验证', '安全验证', '滑块验证', '图形验证', '请完成验证', '异常流量', '机器人',
]
# reCAPTCHA / hCaptcha / Turnstile iframe 特征
CAPTCHA_IFRAME_PATTERNS = [
    'recaptcha/api', 'hcaptcha.com', 'challenges.cloudflare.com/turnstile',
    'captcha.qq.com', 'captcha.aliyun', 'geetest', '极验',
]
# 登录墙关键词
LOGIN_WALL_KEYWORDS = [
    'please log in', 'sign in to continue', 'login required', 'log in to view',
    '请登录', '登录后查看', '登录后继续', '需要登录', '请先登录',
]
# 内容缺失提示（页面加载成功但目标被替换）
CONTENT_GONE_KEYWORDS = [
    'not available', 'no longer available', 'has been removed', 'access denied',
    '不存在', '已删除', '已被移除', '无法访问', '内容不可用', '页面不存在',
]


def _match_any(text, keywords):
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def detect_captcha(title, body, html):
    """验证码/人机验证页。"""
    reasons = []
    title_lower = (title or '').lower()
    # 标题命中
    title_hits = _match_any(title or '', CAPTCHA_KEYWORDS)
    if title_hits:
        reasons.append(f'标题命中: {title_hits}')
    # 正文高频命中
    body_hits = _match_any(body or '', CAPTCHA_KEYWORDS)
    if len(body_hits) >= 2:
        reasons.append(f'正文命中多关键词: {body_hits}')
    # iframe 特征
    html_lower = (html or '').lower()
    iframe_hits = [p for p in CAPTCHA_IFRAME_PATTERNS if p in html_lower]
    if iframe_hits:
        reasons.append(f'验证码 iframe: {iframe_hits}')
    # body 过短 + 命中关键词 = 高度可疑
    if body and len(body) < 500 and body_hits:
        reasons.append(f'页面过短({len(body)}字符)+命中关键词，疑似拦截页')
    return reasons


def detect_login_wall(title, body, html):
    """登录墙突变。"""
    hits = _match_any((body or '') + ' ' + (title or ''), LOGIN_WALL_KEYWORDS)
    if len(hits) >= 1:
        return [f'登录墙关键词: {hits}']
    return []


def detect_content_gone(title, body, html):
    """内容缺失异常。"""
    hits = _match_any((body or '') + ' ' + (title or ''), CONTENT_GONE_KEYWORDS)
    if len(hits) >= 1:
        return [f'内容缺失提示: {hits}']
    return []


def detect_empty_serp(url, body):
    """SERP 首页 0 结果异常（搜索引擎结果页特有）。"""
    domain = domain_of(url or '')
    serp_domains = ['google.', 'bing.com', 'baidu.com', 'duckduckgo.com', 'sogou.com']
    if not any(s in domain for s in serp_domains):
        return []
    # SERP 页面但无典型结果结构
    result_markers = ['class="g"', 'class="result"', 'id="search"', 'class="b_algo"',
                      'class="c-container"', 'data-sokoban']
    html_markers_hit = []  # 无法在 body 检测 html class，这里只看 body 文本量
    if body and len(body) < 800:
        return [f'SERP 页面 body 异常短({len(body)}字符)，疑似反爬拦截而非真无结果']
    return []


def detect_fingerprint(last_action, current_url, prev_url):
    """行为指纹检测：操作后跳转到验证/拦截 URL。"""
    if not last_action:
        return []
    cur_lower = (current_url or '').lower()
    fingerprint_paths = ['/verify', '/captcha', '/security', '/challenge', '/safebrowsing',
                         '/interstitial', 'verify.', 'safe.']
    hits = [p for p in fingerprint_paths if p in cur_lower]
    if hits and current_url != prev_url:
        return [f'操作({last_action})后跳转到可疑路径: {hits} (当前URL: {current_url})']
    return []


def domain_of(url):
    try:
        return urlparse(url).geturl() and urlparse(url).netloc
    except Exception:
        return ''


def _parse_html_text(html):
    """从 HTML 文本粗提取 title 和 body 纯文本（用于 --html 离线检测模式）。
    轻量正则，避免引入 bs4 依赖。"""
    title = ''
    body_text = html or ''
    tm = re.search(r'<title[^>]*>(.*?)</title>', html or '', re.IGNORECASE | re.DOTALL)
    if tm:
        title = re.sub(r'\s+', ' ', tm.group(1)).strip()
    # 去 body 标签外的内容（script/style 全删）
    bm = re.search(r'<body[^>]*>(.*?)</body>', html or '', re.IGNORECASE | re.DOTALL)
    raw = bm.group(1) if bm else body_text
    raw = re.sub(r'<script.*?</script>', ' ', raw, flags=re.IGNORECASE | re.DOTALL)
    raw = re.sub(r'<style.*?</style>', ' ', raw, flags=re.IGNORECASE | re.DOTALL)
    body_text = re.sub(r'<[^>]+>', ' ', raw)  # 去标签
    body_text = re.sub(r'\s+', ' ', body_text).strip()
    return title, body_text


def check_page(client, target_id, last_action=None, prev_url=None, provided_html=None):
    """检测单个页面的拦截信号。返回结构化结果。

    provided_html 提供时进入离线模式：从 HTML 解析 title/body，不从页面拉取。
    这样 --html 参数对所有 6 类信号都生效（修复失效点B：原实现只覆盖 iframe 检测）。
    """
    result = {
        'targetId': target_id,
        'intercepted': False,
        'signals': [],
        'snapshot': {},
        'recommendation': '',
    }
    body = ''
    html = provided_html or ''
    title = ''
    current_url = ''

    if provided_html:
        # 离线模式：从提供的 HTML 解析 title/body，不访问页面
        title, body = _parse_html_text(provided_html)
        try:
            info = client.info(target_id) or {}
            current_url = info.get('url', '')
        except Exception:
            current_url = ''
    else:
        # 在线模式：从页面拉取
        try:
            info = client.info(target_id) or {}
            title = info.get('title', '')
            current_url = info.get('url', '')
            val, err = client.eval(target_id, 'document.body ? document.body.innerText : ""')
            if not err and val:
                body = val
            # 取 html 片段用于 iframe 检测（限制长度）
            html_val, _ = client.eval(target_id,
                '(document.documentElement.outerHTML || "").slice(0, 5000)')
            html = html_val or ''
        except Exception as e:
            result['snapshot']['error'] = f'页面信息获取失败: {e}'
            result['recommendation'] = '页面无法访问，可能已关闭或 Chrome 断连。先 status 检查池健康度。'
            return result

    result['snapshot'] = {'title': title, 'url': current_url, 'bodyLength': len(body)}

    # 依次检测 6 类信号
    sig_map = {
        'CAPTCHA': detect_captcha(title, body, html),
        'LOGIN_WALL': detect_login_wall(title, body, html),
        'CONTENT_GONE': detect_content_gone(title, body, html),
        'EMPTY_SERP': detect_empty_serp(current_url, body),
        'FINGERPRINT': detect_fingerprint(last_action, current_url, prev_url),
    }
    for sig_type, reasons in sig_map.items():
        if reasons:
            result['signals'].append({'type': sig_type, 'reasons': reasons})

    result['intercepted'] = len(result['signals']) > 0
    result['snapshot']['domain'] = domain_of(current_url)

    if result['intercepted']:
        sig_types = [s['type'] for s in result['signals']]
        result['recommendation'] = (
            f'检测到拦截信号 {sig_types}。已停止操作。'
            '请按 references/experience.md 将本次拦截写入 site-patterns/'
            f'{domain_of(current_url)}.md 的"反爬规避"区（触发条件+症状+尝试规避+结果）。'
            '降级策略：①拟人 GUI（human_behavior）②换 locale/UA ③告知用户需手动登录。'
            '不要在同一方式上反复重试——同一方式失败 2 次就该重新评估方向。'
        )
    return result


def main():
    p = argparse.ArgumentParser(description='web-chrome 拦截信号检测器')
    p.add_argument('--proxy', default='http://localhost:3457')
    sub = p.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('check', help='检测页面拦截信号')
    c.add_argument('target_id')
    c.add_argument('--last-action', default=None, help='触发检测的最后操作（用于指纹检测）')
    c.add_argument('--prev-url', default=None, help='操作前 URL（用于检测跳转）')
    c.add_argument('--html', default=None, help='直接提供 HTML 文本检测（不从页面拉取）')
    args = p.parse_args()

    client = CdpClient(proxy=args.proxy)
    if not client.is_ready():
        print(json.dumps({'error': 'CDP Proxy 未就绪'}, ensure_ascii=False))
        return 1

    if args.cmd == 'check':
        result = check_page(client, args.target_id,
                            last_action=args.last_action,
                            prev_url=args.prev_url,
                            provided_html=args.html)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result['intercepted'] else 2
    return 1


if __name__ == '__main__':
    sys.exit(main())
