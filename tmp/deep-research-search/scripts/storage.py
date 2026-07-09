"""存储服务（StorageService）

职责：
  - url_id：URL 派生稳定 id（hash），幂等 key（同一 URL 永远同一 id）
  - manifest：任务级索引（搜索方向 ↔ URL ↔ 数据文件 ↔ 轮次），跨轮跨主题聚合与溯源
  - round 追加：支持 round-N > 6（6 轮默认之上的追加轮次）

设计说明：
  文件命名仍由 url_fetch/cdp_fetch 用 {direction}-{seq}（不破坏下游引用）；
  manifest 用 url_id 作稳定 key 建立 URL↔文件映射，解决溯源；
  幂等重跑靠 manifest 的 url_id 去重（同 URL 覆盖更新，不重复计数）。
"""

import hashlib
import json
import os
import re
from urllib.parse import urlparse


def url_id(url):
    """URL 派生稳定 id：域名简记 + sha1[:10]。同一 URL 永远同一 id（幂等）。"""
    try:
        domain = urlparse(url).netloc.replace('www.', '').split(':')[0].split('.')[0][:12]
    except Exception:
        domain = 'node'
    h = hashlib.sha1(url.encode('utf-8')).hexdigest()[:10]
    slug = re.sub(r'[^a-zA-Z0-9_-]', '', domain) or 'node'
    return f"{slug}-{h}"


def manifest_path(workdir):
    return os.path.join(workdir, '_manifest.json')


def load_manifest(workdir):
    """加载 manifest，不存在则返回空结构。"""
    p = manifest_path(workdir)
    if os.path.exists(p):
        try:
            with open(p, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {'directions': {}, 'urls': {}, 'rounds': []}


def save_manifest(workdir, manifest):
    p = manifest_path(workdir)
    os.makedirs(os.path.dirname(p) or workdir, exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)


def record_url(workdir, url, direction, data_file=None, round_n=None,
               source=None, quality=None, status=None):
    """记录一个 URL 的采集/获取信息到 manifest（幂等：同 url_id 覆盖更新）。"""
    m = load_manifest(workdir)
    uid = url_id(url)
    m['urls'][uid] = {
        'url': url, 'direction': direction,
        'data_file': data_file, 'round': round_n,
        'source': source, 'quality': quality, 'status': status,
    }
    # 方向索引（url_count 重算，幂等不重复计）
    d = m['directions'].setdefault(direction, {'url_count': 0, 'rounds': []})
    d['url_count'] = sum(1 for u in m['urls'].values() if u.get('direction') == direction)
    if round_n and round_n not in d['rounds']:
        d['rounds'].append(round_n)
        d['rounds'].sort()
    if round_n and round_n not in m['rounds']:
        m['rounds'].append(round_n)
        m['rounds'].sort()
    save_manifest(workdir, m)
    return uid


def ensure_round_dir(workdir, round_n):
    """确保 round-N 目录存在（支持 >6 追加）。"""
    for sub in ['urls', 'data']:
        os.makedirs(os.path.join(workdir, sub, f'round-{round_n}'), exist_ok=True)


def manifest_summary(workdir):
    """manifest 摘要（供 scores.md 健康度，P4 用）。"""
    m = load_manifest(workdir)
    return {
        'total_urls': len(m.get('urls', {})),
        'directions': len(m.get('directions', {})),
        'rounds': m.get('rounds', []),
    }
