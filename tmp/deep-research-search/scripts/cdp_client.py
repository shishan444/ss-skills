"""CDP Client（防腐层 ACL）

统一封装与 cdp-proxy 的交互，隔离 proxy 协议变更对业务脚本
（serp_collect / url_fetch / cdp_fetch）的影响。

职责：
  - 连接与健康探活（health / is_ready / wait_ready）
  - TabPool（信号量，上限默认 30，分阶段独占；acquire_tab 返回租约，用完自动释放）
  - 原子组合操作（fetch_url：开页 → 等载 → 提取 → 关页，优先 proxy /fetch 端点）
  - CDP 原生能力封装：Input 鼠标/滚动（isTrusted=true）、Emulation 语言/UA、Network header

设计原则：业务脚本只与本 client 交互，不直接 HTTP 调 proxy。
"""

import threading
import time
import requests

DEFAULT_PROXY = 'http://localhost:3456'
DEFAULT_TAB_POOL = 30


class CdpError(Exception):
    pass


class CdpClient:
    """CDP Proxy 的统一客户端（防腐层）。"""

    def __init__(self, proxy=DEFAULT_PROXY, tab_pool_size=DEFAULT_TAB_POOL, timeout=30):
        self.proxy = proxy.rstrip('/')
        self.timeout = timeout
        self._tab_sem = threading.Semaphore(tab_pool_size)
        # CDP Proxy 是 localhost 服务，必须直连——禁用 trust_env，避免请求被
        # macOS 系统代理（ClashX/Surge 等）转发。代理转发 localhost 在高并发下会超时，
        # 导致 serp_collect 翻页中断（每引擎只能采 1 页）。
        # 注：url_fetch.py 抓外网仍走代理（trust_env 默认开），这里只对 CDP 调用禁用。
        self.session = requests.Session()
        self.session.trust_env = False

    # ---------------- 健康探活 ----------------
    def health(self):
        try:
            return self.session.get(f'{self.proxy}/health', timeout=5).json()
        except Exception:
            return None

    def is_ready(self):
        h = self.health()
        return bool(h and h.get('connected'))

    def wait_ready(self, retries=10, interval=1.0):
        for _ in range(retries):
            if self.is_ready():
                return True
            time.sleep(interval)
        return False

    # ---------------- Tab 池（分阶段独占）----------------
    class TabLease:
        """tab 租约：with 块结束自动关 tab + 释放信号量。"""

        def __init__(self, client, target_id):
            self.client = client
            self.target_id = target_id

        def __enter__(self):
            return self.target_id

        def __exit__(self, *exc):
            try:
                self.client.close(self.target_id)
            finally:
                self.client._tab_sem.release()
            return False

    def acquire_tab(self, url='about:blank'):
        """申请一个 tab（阻塞至 TabPool 有空位），打开 url，返回租约。"""
        self._tab_sem.acquire()
        try:
            tid = self._new(url)
            if not tid:
                raise CdpError('CDP /new 返回空 targetId')
            return self.TabLease(self, tid)
        except Exception:
            self._tab_sem.release()
            raise

    def _new(self, url):
        return self.session.get(f'{self.proxy}/new', params={'url': url}, timeout=self.timeout).json().get('targetId')

    def close(self, target_id):
        try:
            self.session.get(f'{self.proxy}/close', params={'target': target_id}, timeout=10)
        except Exception:
            pass

    def targets(self):
        return self.session.get(f'{self.proxy}/targets', timeout=self.timeout).json()

    # ---------------- 基础操作 ----------------
    def eval(self, target_id, js):
        r = self.session.post(f'{self.proxy}/eval', params={'target': target_id},
                          data=js.encode('utf-8'),
                          headers={'Content-Type': 'text/plain; charset=utf-8'},
                          timeout=self.timeout)
        d = r.json()
        if 'error' in d and 'value' not in d:
            return None, d.get('error', 'eval failed')
        return d.get('value'), None

    def info(self, target_id):
        import json as _j
        r = self.session.get(f'{self.proxy}/info', params={'target': target_id}, timeout=self.timeout)
        try:
            return r.json()
        except Exception:
            try:
                return _j.loads(r.text.strip())
            except Exception:
                return {}

    def navigate(self, target_id, url):
        self.session.get(f'{self.proxy}/navigate', params={'target': target_id, 'url': url}, timeout=self.timeout)

    # ---------------- 原子组合（减少往返）----------------
    def fetch_url(self, url, wait=4, extract_js=None):
        """组合：开 tab → 等待加载 → eval 提取 → 关 tab。
        优先 proxy /fetch 组合端点；不可用则手动 new/eval/close 兜底。"""
        params = {'url': url, 'wait': str(wait)}
        try:
            r = self.session.get(f'{self.proxy}/fetch', params=params, timeout=self.timeout + wait + 5)
            d = r.json()
            if 'error' not in d or 'value' in d:
                return d
        except Exception:
            pass
        with self.acquire_tab(url) as tid:
            time.sleep(wait)
            val, err = self.eval(tid, extract_js or 'document.body ? document.body.innerText : ""')
            return {'value': val, 'error': err}

    # ---------------- CDP 原生：Input（isTrusted=true）----------------
    def mouse_move(self, target_id, points):
        """points: [(x,y),...] 贝塞尔轨迹点。"""
        r = self.session.post(f'{self.proxy}/input/move', params={'target': target_id},
                          json={'points': points}, timeout=self.timeout)
        return r.json()

    def mouse_click(self, target_id, x, y):
        r = self.session.post(f'{self.proxy}/input/click', params={'target': target_id},
                          json={'x': x, 'y': y}, timeout=self.timeout)
        return r.json()

    def scroll(self, target_id, direction='down', y=3000):
        r = self.session.get(f'{self.proxy}/input/scroll',
                         params={'target': target_id, 'direction': direction, 'y': y},
                         timeout=self.timeout)
        return r.json()

    # ---------------- CDP 原生：Emulation / Network（多语言）----------------
    def set_locale(self, target_id, locale='zh-CN', accept_language=None, user_agent=None):
        body = {'locale': locale}
        if accept_language:
            body['acceptLanguage'] = accept_language
        if user_agent:
            body['userAgent'] = user_agent
        r = self.session.post(f'{self.proxy}/emulation/locale', params={'target': target_id},
                          json=body, timeout=self.timeout)
        return r.json()

    def set_headers(self, target_id, headers):
        r = self.session.post(f'{self.proxy}/network/headers', params={'target': target_id},
                          json={'headers': headers}, timeout=self.timeout)
        return r.json()
