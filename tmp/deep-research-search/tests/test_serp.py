"""serp_collect 测试：build_search_url 三引擎分页 + extract_serp JSON 解析。"""
import os
import sys
import json
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))
from serp_collect import build_search_url, extract_serp, collect_keyword
from human_behavior import HumanBehavior
from events import read_events


def test_build_search_url():
    g0 = build_search_url('google', 'rust async', 0)
    g2 = build_search_url('google', 'rust async', 2)
    b1 = build_search_url('bing', 'rust async', 1)
    bd2 = build_search_url('baidu', '测试', 2)

    assert 'google.com/search' in g0 and 'start=' not in g0, f'google 首页无 start: {g0}'
    assert 'start=20' in g2, f'google 第3页 start=20: {g2}'
    assert 'bing.com/search' in b1 and 'first=11' in b1, f'bing 第2页 first=11: {b1}'
    assert 'baidu.com/s' in bd2 and 'pn=20' in bd2, f'baidu 第3页 pn=20: {bd2}'
    print('  build_search_url 三引擎分页 OK')


def test_extract_serp_parse():
    class FakeClient:
        def eval(self, tid, js):
            return json.dumps({
                'urls': ['https://a.com', 'https://b.com'],
                'pagination': {'hasNext': True, 'nextUrl': 'https://next'},
            }), None
    serp = extract_serp(FakeClient(), 'tid', 'script')
    assert serp and serp['urls'] == ['https://a.com', 'https://b.com'], serp
    assert serp['pagination']['hasNext'] is True
    print('  extract_serp JSON 解析 OK')


def test_extract_serp_error():
    class FakeClient:
        def eval(self, tid, js):
            return None, 'eval error'
    assert extract_serp(FakeClient(), 'tid', 'script') is None, 'eval 出错应返回 None'
    print('  extract_serp 错误处理 OK')


def test_extract_serp_dict():
    # eval 返回 dict（非字符串）也应被接受
    class FakeClient:
        def eval(self, tid, js):
            return {'urls': ['https://x.com'], 'pagination': {'hasNext': False}}, None
    serp = extract_serp(FakeClient(), 'tid', 'script')
    assert serp and serp['urls'] == ['https://x.com']
    print('  extract_serp 接收 dict OK')


def test_zero_results_emit():
    """0 结果时 serp_collect 经 collect_keyword 触发 emit(ZERO_RESULTS) 写入 _events.log。"""
    class FakeLease:
        def __init__(self, tid): self.tid = tid
        def __enter__(self): return self.tid
        def __exit__(self, *a): return False

    class FakeClient:
        def acquire_tab(self, url): return FakeLease('tid')
        def eval(self, tid, js):
            return json.dumps({'urls': [], 'pagination': {'hasNext': False}}), None
        def scroll(self, *a, **k): return {}
        def set_locale(self, *a, **k): return {}
        def close(self, *a): pass

    workdir = tempfile.mkdtemp()
    human = HumanBehavior(FakeClient())
    collect_keyword(FakeClient(), human, '生僻词xyz', 2, 'script', 'zh-CN', workdir)
    evs = read_events(workdir, 'ZERO_RESULTS')
    assert len(evs) > 0, '0 结果应 emit ZERO_RESULTS'
    assert evs[0]['payload']['keyword'] == '生僻词xyz'
    print(f'  ZERO_RESULTS emit OK（{len(evs)} 条，三引擎各一）')


if __name__ == '__main__':
    test_build_search_url()
    test_extract_serp_parse()
    test_extract_serp_error()
    test_extract_serp_dict()
    test_zero_results_emit()
    print('serp_collect 测试全部通过 ✓')
