---
domain: www.google.com
aliases: [Google, 谷歌搜索]
updated: 2026-07-06
---
## 平台特征
全球最大搜索引擎。对自动化操作有反爬检测，但 CDP 直连用户日常 Chrome（携带真实登录态 + navigator.webdriver=false）下，正常搜索可工作。
- SERP 结构：结果在 `div.g` / `a h3` 容器内
- 结果页 body 长度通常 > 5000 字符（短于 800 且域名含 google. 可能是反爬拦截，见 intercept_detector EMPTY_SERP）

## 有效模式
- 程序化导航：`https://www.google.com/search?q={urlencoded_query}`（2026-07-06 验证有效）
- 结果 URL 提取 JS：`document.querySelectorAll("a h3")` → `closest("a").href`（2026-07-06 验证）
- 正文提取：`document.body.innerText`（2026-07-06 验证，bodyLength≈7000-10000）
- 搜索词用 `+` 连接，空格转 `+`（2026-07-06 验证）

## 已知陷阱
- 短时间密集开多个 Google 搜索 tab 可能触发频率风控（未实测阈值，保守建议 < 5/分钟）
- Google 结果 URL 有时是 `google.com/url?q=` 跳转链，需解析真实 URL（本次未遇到，CDP 下 a.href 直接是真实链接）

## 反爬规避

### 触发条件
（本次未触发，2026-07-06 单次搜索 + 程序化 eval 提取，正常工作）

### 规避策略
- CDP 直连用户 Chrome（携带登录态）是关键——navigator.webdriver 在 CDP 下默认 false（check-deps.mjs 已验证）
- 程序化 eval 提取 DOM（纯读取，非交互）在单次搜索下可行（2026-07-06 验证）
- 若触发拦截，降级策略：①拟人 GUI（human_behavior 点击搜索框+输入+人类滚动）②减少频率 ③换 locale/UA

### 失败教训
（暂无）
