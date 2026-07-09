"""quality_score 评分测试：五维（长度/段落/标题/中文/信息密度）+ 导航噪声扣分。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from quality import quality_score


def test_short_text():
    r = quality_score('短', '标题')
    assert not r['pass'] and r['score'] == 0, f'过短应 0 分不通过，实际 {r}'
    print('  过短文本 0 分 OK')


def test_high_quality():
    # 长 + 多段落 + 有标题 + 中文 + 高信息密度 → 应通过
    text = '\n'.join([f'这是一段足够长的中文内容，包含足够的信息量用于测试评分系统第{i}段。' for i in range(15)])
    r = quality_score(text, '一个有意义的标题')
    assert r['pass'], f'高质量应通过，实际 {r}'
    assert r['score'] >= 30, f'分数应≥30，实际 {r["score"]}'
    print(f'  高质量通过 OK (score={r["score"]})')


def test_nav_noise():
    # 前 500 字含 >2 个导航词 → 扣 15 分 + 标注
    text = '首页 登录 注册 搜索 上一页\n' + '正文内容' * 80
    r = quality_score(text, '标题')
    assert '导航噪声' in r['reason'], f'应检测出导航噪声，{r}'
    print(f'  导航噪声扣分 OK (score={r["score"]}, reason={r["reason"]})')


def test_no_title():
    text = 'a' * 600  # 长但无标题
    r = quality_score(text, '')
    assert '无有效标题' in r['reason'], f'应标注无标题，{r}'
    print('  无标题标注 OK')


if __name__ == '__main__':
    test_short_text()
    test_high_quality()
    test_nav_noise()
    test_no_title()
    print('quality 测试全部通过 ✓')
