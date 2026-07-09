#!/usr/bin/env node
// web-chrome 环境检查 + Chrome/Proxy 启动
// 移植自 deep-research-search，文案改为 web-chrome，移除 trafilatura 依赖检查（web-chrome 不做正文提取）
// 功能：
//   1. 检查 Node 版本
//   2. 检测 Chrome 远程调试端口（9222）；未开则提示，或用 --launch-chrome 自动启动
//   3. 启动 CDP Proxy
// 用法：
//   node check-deps.mjs                 # 仅检查 + 提示
//   node check-deps.mjs --launch-chrome # 自动退出 Chrome + 带参数重启（默认 profile）

import { spawn, execSync } from 'node:child_process';
import http from 'node:http';
import net from 'node:net';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PROXY_PORT = parseInt(process.env.CDP_PROXY_PORT || '3457');
const PROXY_SCRIPT = path.join(__dirname, 'cdp-proxy.mjs');
const DEBUG_PORT = 9222;

// Chrome 启动参数（默认 profile：CDP + 并发性能 + 恢复 tab）
// 注：不用 --disable-blink-features=AutomationControlled——Chrome 149 提示不受支持，
// 且 CDP 控制（非 ChromeDriver）下 navigator.webdriver 默认为 false（诊断已验证），无需此 flag。
const CHROME_FLAGS = [
  '--remote-debugging-port=9222',                  // 开 CDP 端口（proxy 入口）
  '--disable-background-timer-throttling',         // 后台 tab JS 不降速（并发必需）
  '--restore-last-session',                        // 退出重启后恢复 tab
];

let errors = 0;
let warnings = 0;
const sleep = (ms) => new Promise(r => setTimeout(r, ms));

function chromeBin() {
  if (process.platform === 'darwin') return '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
  if (process.platform === 'win32') return 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  return '/usr/bin/google-chrome'; // linux
}

function checkNodeVersion() {
  const version = process.version;
  const major = parseInt(version.replace('v', ''));
  if (major >= 22) {
    console.log(`[OK] Node.js ${version}（原生 WebSocket）`);
  } else if (major >= 18) {
    console.log(`[WARN] Node.js ${version}（需要 ws 模块，建议升级到 22+）`);
    warnings++;
  } else {
    console.log(`[FAIL] Node.js ${version} 太旧，需要 18+（推荐 22+）`);
    errors++;
  }
}

function checkPythonDeps() {
  try {
    execSync('python3 -c "import requests"', {
      encoding: 'utf-8', timeout: 5000, stdio: ['pipe', 'pipe', 'pipe']
    });
    console.log('[OK] Python 依赖齐全（requests）');
  } catch {
    console.log('[FAIL] Python 依赖缺失（requests）—— cdp_client/tab_manager/intercept_detector 将无法运行');
    console.log('  解决：python3 -m pip install -r ' + path.join(__dirname, 'requirements.txt'));
    errors++;
  }
}

// 探测 Chrome 远程调试端口
function checkDebugPort(port = DEBUG_PORT) {
  return new Promise((resolve) => {
    const s = net.createConnection(port, '127.0.0.1');
    const t = setTimeout(() => { s.destroy(); resolve(false); }, 1000);
    s.once('connect', () => { clearTimeout(t); s.destroy(); resolve(true); });
    s.once('error', () => { clearTimeout(t); resolve(false); });
  });
}

function checkChromeRunning() {
  try {
    const result = execSync('tasklist /FI "IMAGENAME eq chrome.exe" /NH', {
      encoding: 'utf-8', timeout: 5000, stdio: ['pipe', 'pipe', 'pipe']
    });
    if (result.includes('chrome.exe')) { console.log('[OK] Chrome 正在运行'); return true; }
  } catch { /* 非 Windows */ }
  try {
    const result = execSync('pgrep -x chrome || pgrep -x "Google Chrome"', {
      encoding: 'utf-8', timeout: 5000, stdio: ['pipe', 'pipe', 'pipe']
    });
    if (result.trim()) { console.log('[OK] Chrome 正在运行'); return true; }
  } catch { /* 非 Linux/Mac */ }
  console.log('[WARN] Chrome 未检测到运行进程');
  warnings++;
  return false;
}

function printLaunchHint() {
  const bin = chromeBin();
  console.log('[WARN] Chrome 未开启远程调试（9222）。两种方式：');
  console.log('  方式A（命令行，需先 ⌘Q 退出 Chrome）:');
  console.log('    "' + bin + '" ' + CHROME_FLAGS.join(' '));
  console.log('  方式B（GUI，保登录态但有提示）: chrome://inspect/#remote-debugging 勾选 "Allow remote debugging"');
  console.log('  或让本脚本自动启动: node check-deps.mjs --launch-chrome');
}

function printChromeFlagsHint() {
  console.log('[INFO] Chrome 启动参数说明（默认 profile）：');
  console.log('  --remote-debugging-port=9222            开 CDP 端口（proxy 入口）');
  console.log('  --disable-background-timer-throttling   后台 tab JS 不降速（并发采集必需）');
  console.log('  --restore-last-session                  退出重启后恢复 tab');
  console.log('  注：navigator.webdriver 在 CDP 下默认 false（已诊断验证），无需 --disable-blink-features');
}

// --launch-chrome：退出 Chrome + 带参数重启 + 等 9222
async function launchChrome() {
  const bin = chromeBin();
  if (!fs.existsSync(bin)) {
    console.log(`[FAIL] 未找到 Chrome: ${bin}`);
    errors++;
    return false;
  }
  console.log('[INFO] 退出当前 Chrome（--restore-last-session 会恢复 tab，登录态保留）...');
  try { execSync('killall "Google Chrome"', { stdio: 'ignore', timeout: 5000 }); } catch { /* 未运行 */ }
  await sleep(2000);
  console.log('[INFO] 带参数启动 Chrome（默认 profile）：');
  console.log('  ' + bin + ' ' + CHROME_FLAGS.join(' '));
  try {
    spawn(bin, CHROME_FLAGS, { detached: true, stdio: 'ignore' }).unref();
  } catch (e) {
    console.log('[FAIL] 启动失败:', e.message);
    errors++;
    return false;
  }
  for (let i = 0; i < 20; i++) {
    if (await checkDebugPort()) {
      console.log(`[OK] Chrome 9222 就绪（${i + 1}s）`);
      return true;
    }
    await sleep(1000);
  }
  console.log('[FAIL] Chrome 9222 未就绪——可能 Chrome 限制默认 profile，改用方式B（chrome://inspect GUI）');
  errors++;
  return false;
}

function checkProxyHealth() {
  return new Promise((resolve) => {
    const req = http.get(`http://127.0.0.1:${PROXY_PORT}/health`, { timeout: 3000 }, (res) => {
      let data = '';
      res.on('data', c => data += c);
      res.on('end', () => {
        try { resolve(JSON.parse(data)); } catch { resolve(null); }
      });
    });
    req.on('error', () => resolve(null));
    req.on('timeout', () => { req.destroy(); resolve(null); });
  });
}

async function startProxy() {
  console.log(`[INFO] 启动 CDP Proxy（端口 ${PROXY_PORT}）...`);
  try {
    spawn(process.execPath, [PROXY_SCRIPT], { detached: true, stdio: 'ignore' }).unref();
  } catch (e) {
    console.log('[FAIL] 启动 CDP Proxy 失败:', e.message);
    errors++;
    return false;
  }
  return new Promise((resolve) => {
    let retries = 15;
    const poll = setInterval(async () => {
      retries--;
      const health = await checkProxyHealth();
      if (health && health.connected) {
        clearInterval(poll);
        console.log('[OK] CDP Proxy 已就绪并连接 Chrome');
        resolve(true);
      } else if (health && health.status === 'ok') {
        clearInterval(poll);
        console.log('[WARN] CDP Proxy 已就绪但未连接 Chrome（首次操作时重试）');
        warnings++;
        resolve(true);
      } else if (retries <= 0) {
        clearInterval(poll);
        console.log('[FAIL] CDP Proxy 启动超时');
        errors++;
        resolve(false);
      }
    }, 1000);
  });
}

async function main() {
  console.log('=== web-chrome 环境检查 ===\n');
  const launchFlag = process.argv.includes('--launch-chrome');

  checkNodeVersion();
  checkPythonDeps();

  // Chrome 远程调试检测 + 可选启动
  if (await checkDebugPort()) {
    console.log('[OK] Chrome 远程调试已开启（9222）');
  } else if (launchFlag) {
    console.log('[INFO] --launch-chrome：自动启动 Chrome');
    await launchChrome();
  } else {
    printLaunchHint();
    warnings++;
  }

  checkChromeRunning();
  printChromeFlagsHint();

  // Proxy
  const existing = await checkProxyHealth();
  if (existing && existing.connected) {
    console.log('[OK] CDP Proxy 已就绪并连接 Chrome');
  } else if (existing) {
    console.log('[WARN] CDP Proxy 已运行但未连接 Chrome');
    warnings++;
  } else {
    await startProxy();
  }

  console.log(`\n=== 结果：${errors} 错误，${warnings} 警告 ===`);
  process.exit(errors > 0 ? 1 : 0);
}

main();
