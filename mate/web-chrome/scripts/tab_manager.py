#!/usr/bin/env python3
"""Tab 池管理器（15 硬上限 + 11 主动整理触发智能淘汰）— web-chrome skill

设计哲学：浏览器是研究者的书桌，不是无底的回收站。书桌开始拥挤（第11本）时，
不是随机收起一本，而是收起对当前任务最没用的那本。智能淘汰尊重任务语义，而非访问时间。

两层阈值：
  - EVICT_THRESHOLD = 11：达此数时，开新 tab 前必须先淘汰一个（除非 --force）
  - HARD_LIMIT = 15：硬安全上限，绝不突破（cdp-proxy.mjs 在此层兜底）

智能淘汰流程（LLM 判断价值，脚本管理机制）：
  1. `tab_manager.py list` 输出所有 tab 元数据 JSON（url/title/lastUsed/openedAt/task/pinned）
  2. LLM 按 5 维度评分（信息完整度/任务相关性/重访成本/新鲜度/独特性），选最低分者
  3. `tab_manager.py evict <target_id>` 关闭选中 tab
  4. 评分维度详见 references/tab-pool.md

本脚本不替 LLM 做价值判断——它只提供决策所需的元数据和执行淘汰的机械能力。
"""

import argparse
import json
import os
import sys
import time
from urllib.parse import urlparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from cdp_client import CdpClient

# 页面池阈值（与 cdp-proxy.mjs TAB_POOL_LIMIT 对齐）
EVICT_THRESHOLD = 11   # 主动整理触发点：达此数时开新 tab 前必须先淘汰
HARD_LIMIT = 15        # 硬安全上限：cdp-proxy.mjs 在此层兜底拒绝

# 本 skill 自管 tab 的持久状态文件（记录 task 标签、pinned 状态、openedAt）
# 用户已有的 tab 不纳入管理，只管理本 skill 创建的 tab。
STATE_FILE = os.path.join(os.path.expanduser('~'), '.web-chrome-tabs.json')


def load_state():
    """加载本 skill 管理的 tab 状态。"""
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    """保存 tab 状态。"""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f'[WARN] 状态保存失败: {e}', file=sys.stderr)


def now_iso():
    return time.strftime('%Y-%m-%dT%H:%M:%S')


def domain_of(url):
    try:
        return urlparse(url).netloc
    except Exception:
        return ''


def _chrome_tab_count(client):
    """Chrome 当前全局 page tab 数（含用户 baseline + managed）。"""
    try:
        return len(client.targets())
    except Exception:
        return -1


def cmd_status(client):
    """池健康度：连接状态 + Chrome tab 总数 + 本 skill 管理的 tab 数。"""
    health = client.health()
    if not health:
        print(json.dumps({'connected': False, 'error': 'CDP Proxy 未运行'}, ensure_ascii=False, indent=2))
        return 1
    state = load_state()
    # 清理已失效的 tab（Chrome 侧已不存在）
    live_managed = 0
    try:
        targets = client.targets()
        live_ids = {t.get('targetId') for t in targets}
        stale = [tid for tid in state if tid not in live_ids]
        for tid in stale:
            del state[tid]
        if stale:
            save_state(state)
        live_managed = len(state)
    except Exception:
        pass
    chrome_total = health.get('tabCount', -1)
    # managed 实际可用余量 = 硬上限 - Chrome 全局 tab 数（考虑用户 baseline 占用）
    # 失效点C修正：当 baseline 多时，managed 到不了整理线 11 就先撞 Chrome 硬上限 15
    if chrome_total >= 0:
        chrome_capacity_for_managed = max(0, HARD_LIMIT - chrome_total + live_managed)
    else:
        chrome_capacity_for_managed = -1
    effective_limit = min(EVICT_THRESHOLD, chrome_capacity_for_managed) if chrome_capacity_for_managed >= 0 else EVICT_THRESHOLD
    out = {
        'connected': health.get('connected', False),
        'chromePort': health.get('chromePort'),
        'chromeTabCount': chrome_total,
        'tabPoolLimit': health.get('tabPoolLimit', HARD_LIMIT),
        'managedTabCount': live_managed,
        'evictThreshold': EVICT_THRESHOLD,
        'hardLimit': HARD_LIMIT,
        'occupancy': f'{live_managed}/{EVICT_THRESHOLD}(整理线) / {HARD_LIMIT}(硬上限)',
        'needsEvictionBeforeOpen': live_managed >= EVICT_THRESHOLD,
        'chromeCapacityForManaged': chrome_capacity_for_managed,
        'effectiveLimit': effective_limit,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def cmd_list(client):
    """列出本 skill 管理的所有 tab 元数据（供 LLM 评分淘汰决策）。"""
    state = load_state()
    try:
        targets = client.targets()
    except Exception as e:
        print(json.dumps({'error': f'获取 targets 失败: {e}'}, ensure_ascii=False))
        return 1
    live_ids = {t.get('targetId'): t for t in targets}
    # 清理失效状态
    stale = [tid for tid in state if tid not in live_ids]
    for tid in stale:
        del state[tid]
    if stale:
        save_state(state)

    tabs = []
    for tid, meta in state.items():
        t = live_ids.get(tid, {})
        tabs.append({
            'targetId': tid,
            'url': meta.get('url', t.get('url', '')),
            'title': meta.get('title', t.get('title', '')),
            'domain': domain_of(meta.get('url', '')),
            'task': meta.get('task', ''),
            'pinned': meta.get('pinned', False),
            'openedAt': meta.get('openedAt', ''),
            'lastUsed': meta.get('lastUsed', ''),
        })
    # 按 openedAt 排序，便于 LLM 快速浏览
    tabs.sort(key=lambda x: x.get('openedAt', ''))
    print(json.dumps({
        'managedCount': len(tabs),
        'evictThreshold': EVICT_THRESHOLD,
        'hardLimit': HARD_LIMIT,
        'needsEviction': len(tabs) >= EVICT_THRESHOLD,
        'tabs': tabs,
        'hint': ('已达整理线(' + str(EVICT_THRESHOLD) + ')，开新 tab 前需先淘汰。'
                 '请按 references/tab-pool.md 的 5 维度评分，选最低分者执行 evict。')
                if len(tabs) >= EVICT_THRESHOLD else None,
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_acquire(client, url, task=''):
    """开新 tab。达整理线(11)时拒绝并提示先淘汰，除非 --force。"""
    state = load_state()
    managed_count = len(state)
    if managed_count >= EVICT_THRESHOLD:
        print(json.dumps({
            'error': 'TABPOOL_NEAR_LIMIT',
            'managedCount': managed_count,
            'evictThreshold': EVICT_THRESHOLD,
            'message': (f'已管理 {managed_count} 个 tab，达整理线 {EVICT_THRESHOLD}。'
                        '开新 tab 前必须先淘汰一个：先 `tab_manager.py list` 查看元数据，'
                        '按 references/tab-pool.md 5 维度评分，选最低分者 `tab_manager.py evict <id>`。'
                        '确认要强行打开（逼近硬上限 15）可加 --force。'),
        }, ensure_ascii=False, indent=2))
        return 2
    try:
        tid = client._new(url)
    except Exception as e:
        # cdp-proxy 在 Chrome 全局 tab 达 HARD_LIMIT(15) 时返回 429，requests 抛 HTTPError
        msg = str(e)
        if '429' in msg or 'TABPOOL' in msg.upper() or 'TabPool' in msg:
            chrome_total = _chrome_tab_count(client)
            print(json.dumps({
                'error': 'CHROME_TAB_LIMIT_REACHED',
                'chromeTabCount': chrome_total,
                'hardLimit': HARD_LIMIT,
                'managedCount': managed_count,
                'message': (f'Chrome 全局 tab 数已达硬上限 {HARD_LIMIT}'
                            f'（当前 {chrome_total} = 用户baseline + managed {managed_count}）。'
                            '这不是 managed 整理线问题，而是 Chrome 总 tab 耗尽。'
                            '必须先 `tab_manager.py evict <id>` 关闭 managed tab 释放空间。'),
            }, ensure_ascii=False, indent=2))
        else:
            print(json.dumps({'error': f'开 tab 失败: {e}'}, ensure_ascii=False))
        return 1
    if not tid:
        # _new 静默返回空（proxy 未抛异常但创建失败）
        chrome_total = _chrome_tab_count(client)
        print(json.dumps({
            'error': 'NEW_RETURNED_EMPTY',
            'chromeTabCount': chrome_total,
            'hardLimit': HARD_LIMIT,
            'message': (f'CDP /new 返回空 targetId。Chrome 当前 {chrome_total} 个 tab'
                        f'（硬上限 {HARD_LIMIT}）。可能已达 Chrome 全局 tab 上限。'),
        }, ensure_ascii=False, indent=2))
        return 1
    state[tid] = {
        'url': url,
        'task': task,
        'pinned': False,
        'openedAt': now_iso(),
        'lastUsed': now_iso(),
    }
    save_state(state)
    print(json.dumps({
        'targetId': tid,
        'url': url,
        'task': task,
        'managedCount': len(state),
        'remainingBeforeEvict': max(0, EVICT_THRESHOLD - len(state)),
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_evict(client, target_ids):
    """关闭指定 tab（可批量，淘汰决策由 LLM 做出，本命令只执行）。

    修复失效点A：原实现只接受单个 target_id，shell 拼接多 id 时静默失败
    （close 对无效 id 吞异常，state 不清理，wasManaged 误报）。
    现支持 nargs='+' 批量，逐个关闭并汇总，无效 id 明确报错。
    """
    if isinstance(target_ids, str):
        target_ids = [target_ids]
    # 过滤空串（shell 变量前导空格会引入空参数），并对空串明确报错
    target_ids = [t for t in target_ids if t and t.strip()]
    if not target_ids:
        print(json.dumps({'error': '未提供有效 targetId（可能 shell 变量含前导空格）'}, ensure_ascii=False))
        return 1
    state = load_state()
    results = []
    for tid in target_ids:
        meta = state.get(tid)
        closed_ok = True
        try:
            client.close(tid)
        except Exception as e:
            closed_ok = False
            results.append({'targetId': tid, 'closed': False, 'wasManaged': meta is not None,
                            'error': f'close 失败: {e}'})
            continue
        if tid in state:
            del state[tid]
        results.append({'targetId': tid, 'closed': closed_ok, 'wasManaged': meta is not None,
                        'url': meta.get('url') if meta else None})
    save_state(state)
    print(json.dumps({
        'evicted': results,
        'managedCount': len(state),
        'remainingBeforeEvict': max(0, EVICT_THRESHOLD - len(state)),
    }, ensure_ascii=False, indent=2))
    return 0 if all(r.get('closed') for r in results) else 1


def cmd_pin(client, target_id, pinned=True):
    """标记/取消关键 tab（pinned tab 免淘汰）。"""
    state = load_state()
    if target_id not in state:
        print(json.dumps({'error': f'tab {target_id} 不在本 skill 管理中，无法 pin'}, ensure_ascii=False))
        return 1
    state[target_id]['pinned'] = pinned
    state[target_id]['lastUsed'] = now_iso()
    save_state(state)
    print(json.dumps({'targetId': target_id, 'pinned': pinned}, ensure_ascii=False, indent=2))
    return 0


def cmd_touch(client, target_id):
    """更新 tab 的 lastUsed（LLM 在使用某 tab 后可调用，辅助未来评分）。"""
    state = load_state()
    if target_id not in state:
        state[target_id] = {'url': '', 'task': '', 'pinned': False, 'openedAt': now_iso()}
    state[target_id]['lastUsed'] = now_iso()
    save_state(state)
    print(json.dumps({'targetId': target_id, 'lastUsed': state[target_id]['lastUsed']}, ensure_ascii=False, indent=2))
    return 0


def main():
    p = argparse.ArgumentParser(
        description='web-chrome Tab 池管理器（15 硬上限 + 11 智能淘汰）',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
典型流程：
  1. status       # 查看池健康度
  2. acquire URL  # 开 tab（达 11 会被拒，提示先淘汰）
  3. list         # 达整理线时，输出元数据供 LLM 评分
  4. evict <id>   # 淘汰 LLM 选定的最低分 tab
  5. pin <id>     # 标记关键 tab 免淘汰
  6. touch <id>   # 使用 tab 后更新 lastUsed

淘汰评分维度见 references/tab-pool.md。
""")
    p.add_argument('--proxy', default='http://localhost:3457', help='CDP Proxy 地址')
    sub = p.add_subparsers(dest='cmd', required=True)

    sub.add_parser('status', help='池健康度')
    sub.add_parser('list', help='列出管理的 tab 元数据')
    ac = sub.add_parser('acquire', help='开新 tab')
    ac.add_argument('url')
    ac.add_argument('--task', default='', help='任务标签')
    ac.add_argument('--force', action='store_true', help='达整理线仍强行打开（逼近硬上限）')
    ev = sub.add_parser('evict', help='关闭/淘汰 tab（支持批量：evict ID1 ID2 ...）')
    ev.add_argument('target_ids', nargs='+', help='一个或多个 targetId')
    pi = sub.add_parser('pin', help='标记关键 tab（免淘汰）')
    pi.add_argument('target_id')
    up = sub.add_parser('unpin', help='取消关键标记')
    up.add_argument('target_id')
    to = sub.add_parser('touch', help='更新 lastUsed')
    to.add_argument('target_id')

    args = p.parse_args()
    client = CdpClient(proxy=args.proxy)

    if not client.is_ready():
        print(json.dumps({'error': 'CDP Proxy 未就绪，先运行 check-deps.mjs'}, ensure_ascii=False))
        return 1

    if args.cmd == 'status':
        return cmd_status(client)
    if args.cmd == 'list':
        return cmd_list(client)
    if args.cmd == 'acquire':
        if args.force:
            # --force 绕过整理线检查，但仍受 cdp-proxy.mjs 硬上限 15 兜底
            state = load_state()
            try:
                tid = client._new(args.url)
            except Exception as e:
                print(json.dumps({'error': f'开 tab 失败（可能已达硬上限 {HARD_LIMIT}）: {e}'}, ensure_ascii=False))
                return 1
            state[tid] = {'url': args.url, 'task': args.task, 'pinned': False,
                          'openedAt': now_iso(), 'lastUsed': now_iso()}
            save_state(state)
            print(json.dumps({'targetId': tid, 'url': args.url, 'forced': True,
                              'managedCount': len(state)}, ensure_ascii=False, indent=2))
            return 0
        return cmd_acquire(client, args.url, args.task)
    if args.cmd == 'evict':
        return cmd_evict(client, args.target_ids)
    if args.cmd == 'pin':
        return cmd_pin(client, args.target_id, True)
    if args.cmd == 'unpin':
        return cmd_pin(client, args.target_id, False)
    if args.cmd == 'touch':
        return cmd_touch(client, args.target_id)
    return 1


if __name__ == '__main__':
    sys.exit(main())
