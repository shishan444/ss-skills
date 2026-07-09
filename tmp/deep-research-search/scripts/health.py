"""健康度聚合（HealthService）

从 manifest + 各轮报告聚合任务级健康度，追加到 scores.md。
指标：采集达成率 / 获取成功率 / CDP 兜底率 / 图谱节点·洞察数。

用法：
  python health.py <workdir> --round N
（每轮采集+获取+兜底+消化完成后调用一次）
"""

import argparse
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from storage import manifest_summary


def _find_int(pattern, text):
    m = re.search(pattern, text)
    return int(m.group(1)) if m else 0


def parse_serp_report(path):
    """采集报告：方向数/达标/有效URL。"""
    txt = open(path, encoding='utf-8').read()
    d = _find_int(r'搜索方向:\s*(\d+)', txt)
    o = _find_int(r'达标:\s*(\d+)', txt)
    t = _find_int(r'有效 URL 总数:\s*(\d+)', txt)
    return {'directions': d, 'reached': o, 'achieve_rate': (o / d * 100) if d else 0, 'total_urls': t}


def parse_fetch_report(path):
    """获取报告：成功率。"""
    txt = open(path, encoding='utf-8').read()
    s = _find_int(r'成功:\s*(\d+)', txt)
    f = _find_int(r'实际请求:\s*(\d+)', txt)
    return {'fetched': f, 'success': s, 'success_rate': (s / f * 100) if f else 0}


def parse_cdp_report(path):
    """CDP 兜底报告：兜底成功率。"""
    txt = open(path, encoding='utf-8').read()
    s = _find_int(r'成功:\s*(\d+)', txt)
    t = _find_int(r'实际处理:\s*(\d+)', txt)
    return {'handled': t, 'success': s, 'bailout_rate': (s / t * 100) if t else 0}


def graph_stats(workdir):
    """图谱规模（schema-agnostic：节点数 + ### 子节块数）。"""
    graph_dir = os.path.join(workdir, 'graph')
    if not os.path.isdir(graph_dir):
        return {'nodes': 0, 'subblocks': 0}
    nodes = subblocks = 0
    for fn in os.listdir(graph_dir):
        if fn.startswith('_') or not fn.endswith('.md'):
            continue
        content = open(os.path.join(graph_dir, fn), encoding='utf-8').read()
        nodes += 1
        subblocks += len(re.findall(r'^### ', content, re.MULTILINE))
    return {'nodes': nodes, 'subblocks': subblocks}


def collect_round_health(workdir, round_n):
    """聚合单轮健康度（采集/获取/CDP/图谱/manifest）。"""
    rd = f'round-{round_n}'
    health = {'round': round_n, 'collect': None, 'fetch': None, 'cdp': None}
    serp_report = os.path.join(workdir, 'urls', rd, '_report.md')
    if os.path.exists(serp_report):
        health['collect'] = parse_serp_report(serp_report)
    fetch_report = os.path.join(workdir, 'data', rd, '_report.md')
    if os.path.exists(fetch_report):
        health['fetch'] = parse_fetch_report(fetch_report)
    cdp_report = os.path.join(workdir, 'data', rd, '_cdp_report.md')
    if os.path.exists(cdp_report):
        health['cdp'] = parse_cdp_report(cdp_report)
    health['graph'] = graph_stats(workdir)
    health['manifest'] = manifest_summary(workdir)
    return health


def format_health_block(health):
    lines = [f"\n## 第 {health['round']} 轮健康度\n"]
    c = health.get('collect')
    if c:
        lines.append(f"- 采集: {c['reached']}/{c['directions']} 方向达标（{c['achieve_rate']:.0f}%），{c['total_urls']} 有效URL")
    f = health.get('fetch')
    if f:
        lines.append(f"- 获取: {f['success']}/{f['fetched']} 成功（{f['success_rate']:.0f}%）")
    cd = health.get('cdp')
    if cd:
        lines.append(f"- CDP兜底: {cd['success']}/{cd['handled']} 成功（{cd['bailout_rate']:.0f}%）")
    g = health.get('graph', {})
    lines.append(f"- 图谱: {g.get('nodes', 0)} 节点, {g.get('subblocks', 0)} 洞察块")
    m = health.get('manifest', {})
    lines.append(f"- manifest: {m.get('total_urls', 0)} URL, {m.get('directions', 0)} 方向, 轮次 {m.get('rounds', [])}")
    # 健康度阈值提示（软告警）
    alerts = []
    if c and c['achieve_rate'] < 50:
        alerts.append('采集达成率偏低')
    if f and f['success_rate'] < 50:
        alerts.append('获取成功率偏低')
    if alerts:
        lines.append(f"- ⚠ 告警: {'; '.join(alerts)}")
    return '\n'.join(lines) + '\n'


def write_health(workdir, round_n):
    """聚合并追加健康度块到 scores.md。"""
    health = collect_round_health(workdir, round_n)
    scores_path = os.path.join(workdir, 'scores.md')
    with open(scores_path, 'a', encoding='utf-8') as f:
        f.write(format_health_block(health))
    # 领域事件：低健康度告警（emit 到 _events.log）
    alerts = []
    c = health.get('collect')
    f = health.get('fetch')
    if c and c['achieve_rate'] < 50:
        alerts.append('采集达成率偏低')
    if f and f['success_rate'] < 50:
        alerts.append('获取成功率偏低')
    if alerts:
        try:
            from events import emit
            emit(workdir, 'HEALTH_CHANGED', {'round': round_n, 'alerts': alerts})
        except Exception:
            pass
    return health


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='健康度聚合（追加到 scores.md）')
    parser.add_argument('workdir', help='工作目录')
    parser.add_argument('--round', '-r', type=int, required=True, help='轮次编号')
    args = parser.parse_args()
    h = write_health(args.workdir, args.round)
    print(f"健康度已写入 {args.workdir}/scores.md（第 {args.round} 轮）")
