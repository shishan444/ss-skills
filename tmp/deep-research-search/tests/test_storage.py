"""storage 关键路径测试：url_id 幂等 / manifest 幂等 / round 追加 / 覆盖更新。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
import storage


def test_url_id_stable():
    u = 'https://example.com/a?x=1'
    assert storage.url_id(u) == storage.url_id(u), '同 URL 应同 id'
    assert storage.url_id(u) != storage.url_id('https://example.com/b'), '不同 URL 应不同 id'
    print('  url_id 幂等 OK')


def test_manifest_idempotent():
    d = tempfile.mkdtemp()
    storage.record_url(d, 'https://a.com/1', '方向A', round_n=1)
    storage.record_url(d, 'https://a.com/1', '方向A', round_n=1)  # 重跑同 URL
    m = storage.load_manifest(d)
    assert m['directions']['方向A']['url_count'] == 1, '幂等重跑不应重复计数'
    assert 1 in m['rounds'], 'round 应记录'
    print('  manifest 幂等 OK')


def test_round_append():
    d = tempfile.mkdtemp()
    storage.ensure_round_dir(d, 7)  # 追加 round-7（>6）
    assert os.path.isdir(os.path.join(d, 'data', 'round-7'))
    assert os.path.isdir(os.path.join(d, 'urls', 'round-7'))
    print('  round 追加 OK')


def test_record_overwrite():
    """接入 url_fetch/cdp_fetch 后：同 URL 重跑覆盖更新（source/status 变，计数不变）。"""
    d = tempfile.mkdtemp()
    storage.record_url(d, 'https://a.com/1', '方向A', round_n=1, source='download_failed', status='failed')
    storage.record_url(d, 'https://a.com/1', '方向A', round_n=1, source='cdp_proxy', status='success')
    m = storage.load_manifest(d)
    uid = storage.url_id('https://a.com/1')
    assert m['urls'][uid]['source'] == 'cdp_proxy', '覆盖后 source 应更新为 cdp_proxy'
    assert m['urls'][uid]['status'] == 'success'
    assert m['directions']['方向A']['url_count'] == 1, '幂等：仍 1 条'
    print('  record_url 覆盖更新 OK')


if __name__ == '__main__':
    test_url_id_stable()
    test_manifest_idempotent()
    test_round_append()
    test_record_overwrite()
    print('storage 测试全部通过 ✓')
