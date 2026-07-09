"""url_dedup 关键路径测试：标准化 / 广告过滤 / 去重。"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from url_dedup import normalize_url, is_likely_ad, dedup_urls


def test_normalize():
    # 去追踪参数（utm_source 在 TRACKING_PARAMS）
    assert normalize_url('https://example.com/p?utm_source=x&id=1') == 'https://example.com/p?id=1'
    # www 去除 + 域名小写
    assert normalize_url('https://www.Example.com/p/') == 'https://example.com/p'
    print('  normalize_url OK')


def test_ad():
    is_ad, _ = is_likely_ad('https://example.com/click?campaign_id=1')
    assert is_ad, 'click?campaign_id 应识别为广告'
    is_ad2, _ = is_likely_ad('https://example.com/article/1')
    assert not is_ad2, 'article/1 不应识别为广告'
    print('  is_likely_ad OK')


def test_dedup():
    urls = ['https://example.com/a', 'https://example.com/a', 'https://example.com/b']
    r = dedup_urls(urls)
    assert len(r['clean']) == 2, f"去重后应 2 个，实际 {len(r['clean'])}"
    assert r['stats']['duplicates_removed'] == 1
    print('  dedup_urls OK')


if __name__ == '__main__':
    test_normalize()
    test_ad()
    test_dedup()
    print('url_dedup 测试全部通过 ✓')
