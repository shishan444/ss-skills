"""graph_manager 测试：link 双向链 / verify 拓扑校验 / export 概览（schema-agnostic）。"""
import os
import sys
import tempfile
import subprocess

SCRIPTS = os.path.join(os.path.dirname(__file__), '..', 'scripts')
GM = os.path.join(SCRIPTS, 'graph_manager.py')
sys.path.insert(0, SCRIPTS)
import graph_manager as gm


def _write(graph, name, body):
    with open(os.path.join(graph, gm.slugify(name) + '.md'), 'w', encoding='utf-8') as f:
        f.write(f'# {name}\n\n{body}')


def _run(graph, *args):
    return subprocess.run([sys.executable, GM, '-g', graph, *args],
                          capture_output=True, text=True)


def test_link_verify_export():
    d = tempfile.mkdtemp()
    _write(d, '概念A', '## 核心判断\nA 的判断')
    _write(d, '概念B', '## 核心判断\nB 的判断')

    r = _run(d, 'link', '概念A', '概念B', '-t', '相关')
    assert r.returncode == 0, f'link 应成功: {r.stderr}'

    r2 = _run(d, 'verify')
    assert '验证通过' in r2.stdout, f'verify 应通过: {r2.stdout}'

    r3 = _run(d, 'export')
    assert r3.returncode == 0, f'export 失败: {r3.stderr}'
    assert os.path.exists(os.path.join(d, '_overview.md')), '应生成 _overview.md'
    assert '概念A' in r3.stdout, 'export 输出应含节点名'
    print('  link→verify→export 全链 OK')


def test_verify_detects_missing_reverse():
    # 手动制造单向链接（X 链 Y，Y 没链 X）→ verify 应报缺反向链接
    d = tempfile.mkdtemp()
    _write(d, 'X', '## 核心判断\n[[Y]] 相关')
    _write(d, 'Y', '## 核心判断\nY 的判断')  # 无 [[X]]
    r = _run(d, 'verify')
    assert r.returncode != 0, '缺反向链接应 verify 失败'
    assert '缺少反向链接' in r.stdout, f'应报缺反向: {r.stdout}'
    print('  verify 检测缺反向链接 OK')


def test_verify_detects_thin_node():
    # 无核心判断且正文 <200 字 → verify 应报内容过少
    d = tempfile.mkdtemp()
    _write(d, '瘦节点', '内容太短')
    r = _run(d, 'verify')
    assert r.returncode != 0, '瘦节点应 verify 失败'
    assert '内容过少' in r.stdout, f'应报内容过少: {r.stdout}'
    print('  verify 检测瘦节点 OK')


if __name__ == '__main__':
    test_link_verify_export()
    test_verify_detects_missing_reverse()
    test_verify_detects_thin_node()
    print('graph_manager 测试全部通过 ✓')
