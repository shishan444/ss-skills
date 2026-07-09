#!/usr/bin/env node
// CDP Proxy - HTTP API 操控用户日常 Chrome（deep-research-search 专用）
// 要求：Chrome 已开启 remote-debugging
// Node.js 22+（原生 WebSocket），< 22 需安装 ws 模块
//
// 端点（v2，已清理 9 个无调用方的死端点）：
//   基础    /health /targets /new /close /navigate /info
//   JS 注入 /eval（纯 DOM 读取）
//   原生    /fetch（组合）/input/move|click|scroll /emulation/locale /network/headers
// TabPool 硬上限：TAB_POOL_LIMIT（默认 30），防资源耗尽

import http from 'node:http';
import { URL } from 'node:url';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import net from 'node:net';

const PORT = parseInt(process.env.CDP_PROXY_PORT || '3456');
const TAB_POOL_LIMIT = parseInt(process.env.CDP_PROXY_TAB_LIMIT || '30');
let ws = null;
let cmdId = 0;
const pending = new Map();
const sessions = new Map();

// WebSocket 兼容层
let WS;
if (typeof globalThis.WebSocket !== 'undefined') {
  WS = globalThis.WebSocket;
} else {
  try {
    WS = (await import('ws')).default;
  } catch {
    console.error('[CDP Proxy] Node.js < 22 且未安装 ws 模块');
    console.error('  解决：升级到 Node.js 22+ 或 npm install -g ws');
    process.exit(1);
  }
}

// 自动发现 Chrome 调试端口
async function discoverChromePort() {
  const possiblePaths = [];
  const platform = os.platform();

  if (platform === 'darwin') {
    const home = os.homedir();
    possiblePaths.push(
      path.join(home, 'Library/Application Support/Google/Chrome/DevToolsActivePort'),
      path.join(home, 'Library/Application Support/Google/Chrome Canary/DevToolsActivePort'),
      path.join(home, 'Library/Application Support/Chromium/DevToolsActivePort'),
    );
  } else if (platform === 'linux') {
    const home = os.homedir();
    possiblePaths.push(
      path.join(home, '.config/google-chrome/DevToolsActivePort'),
      path.join(home, '.config/chromium/DevToolsActivePort'),
    );
  } else if (platform === 'win32') {
    const localAppData = process.env.LOCALAPPDATA || '';
    possiblePaths.push(
      path.join(localAppData, 'Google/Chrome/User Data/DevToolsActivePort'),
      path.join(localAppData, 'Chromium/User Data/DevToolsActivePort'),
    );
  }

  for (const p of possiblePaths) {
    try {
      const content = fs.readFileSync(p, 'utf-8').trim();
      const lines = content.split('\n');
      const port = parseInt(lines[0]);
      if (port > 0 && port < 65536) {
        const ok = await checkPort(port);
        if (ok) {
          const wsPath = lines[1] || null;
          console.log(`[CDP Proxy] DevToolsActivePort 发现端口: ${port}${wsPath ? ' (wsPath)' : ''}`);
          return { port, wsPath };
        }
      }
    } catch { /* 文件不存在 */ }
  }

  const commonPorts = [9222, 9229, 9333];
  for (const port of commonPorts) {
    const ok = await checkPort(port);
    if (ok) {
      console.log(`[CDP Proxy] 扫描发现端口: ${port}`);
      return { port, wsPath: null };
    }
  }

  return null;
}

function checkPort(port) {
  return new Promise((resolve) => {
    const socket = net.createConnection(port, '127.0.0.1');
    const timer = setTimeout(() => { socket.destroy(); resolve(false); }, 2000);
    socket.once('connect', () => { clearTimeout(timer); socket.destroy(); resolve(true); });
    socket.once('error', () => { clearTimeout(timer); resolve(false); });
  });
}

function getWebSocketUrl(port, wsPath) {
  if (wsPath) return `ws://127.0.0.1:${port}${wsPath}`;
  return `ws://127.0.0.1:${port}/devtools/browser`;
}

let chromePort = null;
let chromeWsPath = null;
let connectingPromise = null;

async function connect() {
  if (ws && (ws.readyState === WS.OPEN || ws.readyState === 1)) return;
  if (connectingPromise) return connectingPromise;

  if (!chromePort) {
    const discovered = await discoverChromePort();
    if (!discovered) {
      throw new Error(
        'Chrome 未开启远程调试。\n' +
        '  打开 chrome://inspect/#remote-debugging，勾选 "Allow remote debugging"\n' +
        '  或启动时加 --remote-debugging-port=9222'
      );
    }
    chromePort = discovered.port;
    chromeWsPath = discovered.wsPath;
  }

  const wsUrl = getWebSocketUrl(chromePort, chromeWsPath);

  return connectingPromise = new Promise((resolve, reject) => {
    ws = new WS(wsUrl);

    const onOpen = () => {
      cleanup();
      connectingPromise = null;
      console.log(`[CDP Proxy] 已连接 Chrome (端口 ${chromePort})`);
      resolve();
    };
    const onError = (e) => {
      cleanup();
      connectingPromise = null;
      ws = null;
      chromePort = null;
      chromeWsPath = null;
      console.error('[CDP Proxy] 连接错误，端口缓存已清除');
      reject(new Error(e.message || '连接失败'));
    };
    const onClose = () => {
      ws = null;
      chromePort = null;
      chromeWsPath = null;
      sessions.clear();
    };
    const onMessage = (evt) => {
      const data = typeof evt === 'string' ? evt : (evt.data || evt);
      const msg = JSON.parse(typeof data === 'string' ? data : data.toString());

      if (msg.method === 'Target.attachedToTarget') {
        sessions.set(msg.params.targetInfo.targetId, msg.params.sessionId);
      }
      if (msg.method === 'Target.detachedFromTarget') {
        // v2: 修会话泄漏——target 分离时清理 session 映射
        const tid = msg.params?.targetId;
        if (tid) sessions.delete(tid);
      }
      if (msg.method === 'Fetch.requestPaused') {
        const { requestId, sessionId: sid } = msg.params;
        sendCDP('Fetch.failRequest', { requestId, errorReason: 'ConnectionRefused' }, sid).catch(() => {});
      }
      if (msg.id && pending.has(msg.id)) {
        const { resolve, timer } = pending.get(msg.id);
        clearTimeout(timer);
        pending.delete(msg.id);
        resolve(msg);
      }
    };

    function cleanup() {
      ws.removeEventListener?.('open', onOpen);
      ws.removeEventListener?.('error', onError);
    }

    if (ws.on) {
      ws.on('open', onOpen);
      ws.on('error', onError);
      ws.on('close', onClose);
      ws.on('message', onMessage);
    } else {
      ws.addEventListener('open', onOpen);
      ws.addEventListener('error', onError);
      ws.addEventListener('close', onClose);
      ws.addEventListener('message', onMessage);
    }
  });
}

function sendCDP(method, params = {}, sessionId = null) {
  return new Promise((resolve, reject) => {
    if (!ws || (ws.readyState !== WS.OPEN && ws.readyState !== 1)) {
      return reject(new Error('WebSocket 未连接'));
    }
    const id = ++cmdId;
    const msg = { id, method, params };
    if (sessionId) msg.sessionId = sessionId;
    const timer = setTimeout(() => {
      pending.delete(id);
      reject(new Error('CDP 命令超时: ' + method));
    }, 30000);
    pending.set(id, { resolve, timer });
    ws.send(JSON.stringify(msg));
  });
}

const portGuardedSessions = new Set();

async function ensureSession(targetId) {
  if (sessions.has(targetId)) return sessions.get(targetId);
  const resp = await sendCDP('Target.attachToTarget', { targetId, flatten: true });
  if (resp.result?.sessionId) {
    const sid = resp.result.sessionId;
    sessions.set(targetId, sid);
    await enablePortGuard(sid);
    return sid;
  }
  throw new Error('attach 失败: ' + JSON.stringify(resp.error));
}

async function enablePortGuard(sessionId) {
  if (!chromePort || portGuardedSessions.has(sessionId)) return;
  try {
    await sendCDP('Fetch.enable', {
      patterns: [
        { urlPattern: `http://127.0.0.1:${chromePort}/*`, requestStage: 'Request' },
        { urlPattern: `http://localhost:${chromePort}/*`, requestStage: 'Request' },
      ]
    }, sessionId);
    portGuardedSessions.add(sessionId);
  } catch { /* 非致命 */ }
}

async function waitForLoad(sessionId, timeoutMs = 15000) {
  await sendCDP('Page.enable', {}, sessionId);
  return new Promise((resolve) => {
    let resolved = false;
    const done = (result) => {
      if (resolved) return;
      resolved = true;
      clearTimeout(timer);
      clearInterval(checkInterval);
      resolve(result);
    };
    const timer = setTimeout(() => done('timeout'), timeoutMs);
    const checkInterval = setInterval(async () => {
      try {
        const resp = await sendCDP('Runtime.evaluate', {
          expression: 'document.readyState',
          returnByValue: true,
        }, sessionId);
        if (resp.result?.result?.value === 'complete') done('complete');
      } catch { /* 忽略 */ }
    }, 500);
  });
}

async function readBody(req) {
  let body = '';
  for await (const chunk of req) body += chunk;
  return body;
}

// v2: TabPool 硬上限保护——返回当前 page tab 数
async function getTabCount() {
  try {
    const resp = await sendCDP('Target.getTargets');
    return resp.result.targetInfos.filter(t => t.type === 'page').length;
  } catch {
    return 0;
  }
}

async function checkTabPool() {
  const count = await getTabCount();
  if (count >= TAB_POOL_LIMIT) {
    const err = new Error(`TabPool 达上限 ${TAB_POOL_LIMIT}（当前 ${count}）`);
    err.code = 'TABPOOL_FULL';
    throw err;
  }
  return count;
}

// HTTP API
const server = http.createServer(async (req, res) => {
  const parsed = new URL(req.url, `http://localhost:${PORT}`);
  const pathname = parsed.pathname;
  const q = Object.fromEntries(parsed.searchParams);

  res.setHeader('Content-Type', 'application/json; charset=utf-8');

  try {
    if (pathname === '/health') {
      const connected = ws && (ws.readyState === WS.OPEN || ws.readyState === 1);
      const tabCount = connected ? await getTabCount().catch(() => -1) : -1;
      res.end(JSON.stringify({ status: 'ok', connected, sessions: sessions.size, chromePort, tabCount, tabPoolLimit: TAB_POOL_LIMIT }));
      return;
    }

    await connect();

    if (pathname === '/targets') {
      const resp = await sendCDP('Target.getTargets');
      const pages = resp.result.targetInfos.filter(t => t.type === 'page');
      res.end(JSON.stringify(pages, null, 2));
    }

    else if (pathname === '/new') {
      const targetUrl = q.url || 'about:blank';
      if (targetUrl !== 'about:blank') await checkTabPool();
      const resp = await sendCDP('Target.createTarget', { url: targetUrl, background: true });
      const targetId = resp.result.targetId;
      if (targetUrl !== 'about:blank') {
        try {
          const sid = await ensureSession(targetId);
          await waitForLoad(sid);
        } catch { /* 非致命 */ }
      }
      res.end(JSON.stringify({ targetId }));
    }

    else if (pathname === '/close') {
      const resp = await sendCDP('Target.closeTarget', { targetId: q.target });
      sessions.delete(q.target);
      res.end(JSON.stringify(resp.result));
    }

    else if (pathname === '/navigate') {
      const sid = await ensureSession(q.target);
      await sendCDP('Page.navigate', { url: q.url }, sid);
      await waitForLoad(sid);
      res.end(JSON.stringify({ ok: true }));
    }

    else if (pathname === '/eval') {
      const sid = await ensureSession(q.target);
      const body = await readBody(req);
      const expr = body || q.expr || 'document.title';
      const resp = await sendCDP('Runtime.evaluate', {
        expression: expr,
        returnByValue: true,
        awaitPromise: true,
      }, sid);
      if (resp.result?.result?.value !== undefined) {
        res.end(JSON.stringify({ value: resp.result.result.value }));
      } else if (resp.result?.exceptionDetails) {
        res.statusCode = 400;
        res.end(JSON.stringify({ error: resp.result.exceptionDetails.text }));
      } else {
        res.end(JSON.stringify(resp.result));
      }
    }

    else if (pathname === '/info') {
      const sid = await ensureSession(q.target);
      const resp = await sendCDP('Runtime.evaluate', {
        expression: 'JSON.stringify({title: document.title, url: location.href, ready: document.readyState})',
        returnByValue: true,
      }, sid);
      res.end(resp.result?.result?.value || '{}');
    }

    // ===== v2 新增：原子组合 =====
    else if (pathname === '/fetch') {
      const url = q.url;
      const wait = parseFloat(q.wait || '4');
      if (!url) { res.statusCode = 400; res.end(JSON.stringify({ error: '缺少 url' })); return; }
      await checkTabPool();
      const resp = await sendCDP('Target.createTarget', { url, background: true });
      const targetId = resp.result.targetId;
      try {
        const sid = await ensureSession(targetId);
        await waitForLoad(sid);
        if (wait > 0) await new Promise(r => setTimeout(r, wait * 1000));
        const extractJs = `(function(){try{var t=document.title||'';var s=['article','[role=article]','main','.article-content','.article-body','.post-body','.entry-content','.content-body','#content','.content'];var el=null;for(var i=0;i<s.length;i++){var c=document.querySelector(s[i]);if(c&&c.innerText.trim().length>200){el=c;break;}}if(!el){var b=document.body?document.body.innerText.trim():'';return JSON.stringify(b.length<200?{success:false,error:'内容过短',title:t}:{success:true,title:t,content:b});}var x=el.innerText.replace(/\\n{3,}/g,'\\n\\n').trim();return JSON.stringify({success:true,title:t,content:x});}catch(e){return JSON.stringify({success:false,error:e.message});}})()`;
        const er = await sendCDP('Runtime.evaluate', { expression: extractJs, returnByValue: true, awaitPromise: true }, sid);
        res.end(JSON.stringify({ value: er.result?.result?.value, targetId }));
      } catch (e) {
        res.end(JSON.stringify({ error: e.message }));
      } finally {
        sendCDP('Target.closeTarget', { targetId }).catch(() => {});
        sessions.delete(targetId);
      }
    }

    // ===== v2 新增：CDP Input domain（isTrusted=true）=====
    else if (pathname === '/input/move') {
      const sid = await ensureSession(q.target);
      const data = JSON.parse((await readBody(req)) || '{}');
      const points = data.points || [];
      for (const pt of points) {
        const x = Array.isArray(pt) ? pt[0] : pt.x;
        const y = Array.isArray(pt) ? pt[1] : pt.y;
        await sendCDP('Input.dispatchMouseEvent', { type: 'mouseMoved', x, y, button: 'none' }, sid);
        await new Promise(r => setTimeout(r, 8 + Math.random() * 20));
      }
      res.end(JSON.stringify({ moved: points.length }));
    }

    else if (pathname === '/input/click') {
      const sid = await ensureSession(q.target);
      const data = JSON.parse((await readBody(req)) || '{}');
      const x = data.x ?? 0, y = data.y ?? 0;
      await sendCDP('Input.dispatchMouseEvent', { type: 'mousePressed', x, y, button: 'left', clickCount: 1 }, sid);
      await new Promise(r => setTimeout(r, 30 + Math.random() * 50));
      await sendCDP('Input.dispatchMouseEvent', { type: 'mouseReleased', x, y, button: 'left', clickCount: 1 }, sid);
      res.end(JSON.stringify({ clicked: true, x, y }));
    }

    else if (pathname === '/input/scroll') {
      const sid = await ensureSession(q.target);
      const direction = q.direction || 'down';
      const y = Math.abs(parseInt(q.y || '3000'));
      if (direction === 'top' || direction === 'bottom') {
        const js = direction === 'top' ? 'window.scrollTo(0,0)' : 'window.scrollTo(0,document.body.scrollHeight)';
        await sendCDP('Runtime.evaluate', { expression: js }, sid);
      } else {
        const dist = direction === 'up' ? -y : y;
        await sendCDP('Input.synthesizeScrollGesture', { x: 400, y: 400, yDistance: dist }, sid);
      }
      await new Promise(r => setTimeout(r, 800));
      res.end(JSON.stringify({ scrolled: direction, distance: y }));
    }

    // ===== v2 新增：Emulation / Network（多语言）=====
    else if (pathname === '/emulation/locale') {
      const sid = await ensureSession(q.target);
      const data = JSON.parse((await readBody(req)) || '{}');
      if (data.locale) {
        try { await sendCDP('Emulation.setLocaleOverride', { locale: data.locale }, sid); } catch { /* 非致命 */ }
      }
      if (data.userAgent || data.acceptLanguage) {
        try {
          await sendCDP('Network.enable', {}, sid);
          await sendCDP('Emulation.setUserAgentOverride', {
            userAgent: data.userAgent || undefined,
            acceptLanguage: data.acceptLanguage || undefined,
          }, sid);
        } catch { /* 非致命 */ }
      }
      res.end(JSON.stringify({ set: true, locale: data.locale, acceptLanguage: data.acceptLanguage }));
    }

    else if (pathname === '/network/headers') {
      const sid = await ensureSession(q.target);
      const data = JSON.parse((await readBody(req)) || '{}');
      await sendCDP('Network.enable', {}, sid);
      await sendCDP('Network.setExtraHTTPHeaders', { headers: data.headers || {} }, sid);
      res.end(JSON.stringify({ set: Object.keys(data.headers || {}) }));
    }

    else {
      res.statusCode = 404;
      res.end(JSON.stringify({
        error: '未知端点',
        endpoints: {
          '/health': 'GET - 健康检查（含 tabCount/tabPoolLimit）',
          '/targets': 'GET - 列出所有 tab',
          '/new?url=': 'GET - 创建后台 tab（TabPool 保护）',
          '/close?target=': 'GET - 关闭 tab',
          '/navigate?target=&url=': 'GET - 导航',
          '/info?target=': 'GET - 页面信息',
          '/eval?target=': 'POST body=JS - 执行 JS（纯 DOM 读取）',
          '/fetch?url=&wait=': 'GET - 组合获取（new+eval+close）',
          '/input/move?target=': 'POST json={points:[[x,y]...]} - 鼠标轨迹（isTrusted）',
          '/input/click?target=': 'POST json={x,y} - 点击（isTrusted）',
          '/input/scroll?target=&direction=&y=': 'GET - 协议级滚动',
          '/emulation/locale?target=': 'POST json={locale,acceptLanguage,userAgent} - 语言/UA',
          '/network/headers?target=': 'POST json={headers:{}} - 额外请求头',
        },
      }));
    }
  } catch (e) {
    res.statusCode = e.code === 'TABPOOL_FULL' ? 429 : 500;
    res.end(JSON.stringify({ error: e.message }));
  }
});

function checkPortAvailable(port) {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.once('error', () => resolve(false));
    s.once('listening', () => { s.close(); resolve(true); });
    s.listen(port, '127.0.0.1');
  });
}

async function main() {
  const available = await checkPortAvailable(PORT);
  if (!available) {
    try {
      const ok = await new Promise((resolve) => {
        http.get(`http://127.0.0.1:${PORT}/health`, { timeout: 2000 }, (res) => {
          let d = '';
          res.on('data', c => d += c);
          res.on('end', () => resolve(d.includes('"ok"')));
        }).on('error', () => resolve(false));
      });
      if (ok) {
        console.log(`[CDP Proxy] 已有实例运行在端口 ${PORT}，退出`);
        process.exit(0);
      }
    } catch { /* 端口占用但非 proxy */ }
    console.error(`[CDP Proxy] 端口 ${PORT} 已被占用`);
    process.exit(1);
  }

  server.listen(PORT, '127.0.0.1', () => {
    console.log(`[CDP Proxy] 运行在 http://localhost:${PORT}（TabPool 上限 ${TAB_POOL_LIMIT}）`);
    connect().catch(e => console.error('[CDP Proxy] 初始连接失败:', e.message, '（首次请求时重试）'));
  });
}

process.on('uncaughtException', (e) => console.error('[CDP Proxy] 未捕获异常:', e.message));
process.on('unhandledRejection', (e) => console.error('[CDP Proxy] 未处理拒绝:', e?.message || e));

main();
