---
domain: github.com
last_updated: 2026-07-14
---

# github.com 站点经验

## 已知行为

### Stars 页面分页（重要）
- URL `?page=N` **不生效**。GitHub 使用 **cursor-based 分页**，必须带 `?after=<base64-cursor>&page=N&tab=stars`。
- 每页 30 个 starred 仓库。页面底部 `<a>Nexthref` 形如：
  `https://github.com/USER?after=Y3Vyc29yOn...&page=2&tab=stars`
- 必须从 page=1 DOM 里抓 `Next` 链接拿 cursor，再导航到 page=2，以此类推。
- 误用 `?page=2` 直接导航 → 返回内容与 page=1 相同，且不报错。

### 抓取 starred 列表的最稳路径
1. 打开 `https://github.com/USER?tab=stars`
2. `document.querySelectorAll("h3 a")` 取仓库名 + href
3. 找 `Next` 按钮：`Array.from(document.querySelectorAll("a")).filter(a=>a.innerText.trim()==="Next").map(a=>a.href)`
4. 导航到 Next URL，重复直至没有 Next

### Raw README 抓取
- 公开仓库 README 用 curl 直接抓，**无需登录态**：
  `https://raw.githubusercontent.com/OWNER/REPO/main/README.md`
- main 不在时回退 master，回退 HEAD。
- 部分仓库使用 `README_zh.md` / `README.zh.md` / `README_CN.md`。

### 已登录态
- 浏览器 profile 已登录时，stars 页面右上显示 `Stars 83 (83)`（数字会随总数变化）。
- 不需要额外登录操作。

## 触发的拦截/异常
- 暂无（2026-07-14 单次任务中未触发风控）。
- 操作节奏：分页 + eval + curl 三种模式穿插，未触发验证码或速率限制。

## 推荐降级策略
- 速率限制时：改用 GitHub API（`api.github.com/users/USER/starred?per_page=100`），未认证 60 次/小时。
- API 仍受限：用浏览器内 `fetch()`（带 cookie）调相同 URL。
