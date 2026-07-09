"""质量评分（单一来源）

url_fetch.py 与 cdp_fetch.py 共用，避免双份漂移。
满分 100，≥30 通过。包含导航噪声检测（-15）。

维度：长度(30) + 段落(20) + 标题(10) + 中文(15) + 信息密度(25)，扣分：导航噪声(-15)
"""

import re


def quality_score(text, title=''):
    """页面正文质量评分。"""
    if not text or len(text.strip()) < 100:
        return {'score': 0, 'reason': '内容过短', 'pass': False}

    score = 0
    reasons = []

    # 长度分（0-30）
    text_len = len(text.strip())
    if text_len > 2000:
        score += 30
    elif text_len > 1000:
        score += 25
    elif text_len > 500:
        score += 20
    elif text_len > 200:
        score += 10
    else:
        score += 5

    # 段落分（0-20）
    paragraphs = [p for p in text.split('\n') if p.strip()]
    para_count = len(paragraphs)
    if para_count > 10:
        score += 20
    elif para_count > 5:
        score += 15
    elif para_count > 2:
        score += 10
    else:
        score += 5

    # 标题分（0-10）
    if title and len(title) > 3:
        score += 10
    else:
        reasons.append('无有效标题')

    # 中文内容加分（0-15）
    chinese_chars = len(re.findall(r'[一-鿿]', text))
    if chinese_chars > 500:
        score += 15
    elif chinese_chars > 100:
        score += 10
    elif chinese_chars > 20:
        score += 5

    # 信息密度分（0-25）
    meaningful_lines = [l for l in text.split('\n') if len(l.strip()) > 30]
    if len(meaningful_lines) > 15:
        score += 25
    elif len(meaningful_lines) > 8:
        score += 20
    elif len(meaningful_lines) > 3:
        score += 15
    else:
        score += 5
        reasons.append('信息密度低')

    # 导航噪声检测（-15）
    nav_signals = sum(
        1 for kw in ['跳转到内容', '搜索', '登录', '注册', '首页', '上一页', '下一页']
        if kw in text[:500]
    )
    if nav_signals > 2:
        score -= 15
        reasons.append('疑似包含导航噪声')

    return {
        'score': max(0, score),
        'reason': '; '.join(reasons) if reasons else '正常',
        'pass': score >= 30,
    }
