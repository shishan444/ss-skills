"""领域事件（Domain Events）

轻量事件记录，供可观测与告警。事件追加到 workdir/_events.log。
设计极简：emit 写日志（JSONL）+ ZERO_RESULTS 同步打 stderr 醒目告警。
不做复杂事件总线——够用即可。

接入点：
  - serp_collect：某引擎 0 结果 → emit ZERO_RESULTS
  - cdp_fetch：兜底完成 → emit FETCH_COMPLETED
  - health.py：低健康度 → emit HEALTH_CHANGED
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EVENT_TYPES = {
    'ACQUISITION_COMPLETED': '采集轮完成',
    'ACQUISITION_FAILED': '采集轮失败',
    'ZERO_RESULTS': '某引擎 0 结果（选择器可能失效/被反爬）',
    'FETCH_COMPLETED': '内容获取完成',
    'HEALTH_CHANGED': '健康度变化/告警',
}


def _events_path(workdir):
    return os.path.join(workdir, '_events.log')


def emit(workdir, event_type, payload=None):
    """发布事件（追加到 _events.log）。未知类型忽略。"""
    if event_type not in EVENT_TYPES:
        return None
    entry = {
        'ts': time.time(),
        'type': event_type,
        'desc': EVENT_TYPES[event_type],
        'payload': payload or {},
    }
    p = _events_path(workdir)
    os.makedirs(os.path.dirname(p) or workdir, exist_ok=True)
    with open(p, 'a', encoding='utf-8') as f:
        f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    # ZERO_RESULTS 同步 stderr（醒目告警，防静默失败）
    if event_type == 'ZERO_RESULTS':
        print(f"[事件] ZERO_RESULTS: {payload}", file=sys.stderr)
    return entry


def read_events(workdir, event_type=None):
    """读取事件（可按类型过滤）。"""
    p = _events_path(workdir)
    if not os.path.exists(p):
        return []
    events = []
    for line in open(p, encoding='utf-8'):
        line = line.strip()
        if not line:
            continue
        try:
            e = json.loads(line)
            if event_type is None or e.get('type') == event_type:
                events.append(e)
        except Exception:
            continue
    return events


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='领域事件查看')
    parser.add_argument('workdir')
    parser.add_argument('--type', default=None, help='按类型过滤')
    args = parser.parse_args()
    for e in read_events(args.workdir, args.type):
        print(f"{e['type']:24s} {e['desc']}  {e['payload']}")
