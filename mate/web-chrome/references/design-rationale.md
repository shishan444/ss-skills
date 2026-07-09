# 设计追溯：web-chrome

> 本文件是 web-chrome 的自带记忆——记录设计决策（D）、失败模式（F）、版本演进。
> 用户带执行反馈/拦截案例回来时，读此文件定位失效点，针对性修正（迭代协议）。
> 随执行反馈持续填充 F1-Fn。

## 定位

web-chrome 是为 agent 提供自动化上网能力的**通用浏览原语**（agent 的"眼睛和手"）。
它替代过时的 `web-access`，成为新的统一联网入口。

**学习对象**：deep-research-search 的现代 CDP 工程（cdp-proxy.mjs + cdp_client.py 防腐层 + human_behavior.py 拟人引擎）。
**不学习**：deep-research-search 的研究工作流（6轮迭代/知识图谱/报告锻造）——那是它自己的领域。

## 设计决策记录

### D1：为何选 CDP Proxy 而非 chrome-devtools / playwright MCP

- **决策**：自建 CDP Proxy（HTTP API @localhost:**3457**）直连用户日常 Chrome
- **端口独立**：web-chrome 用 3457，deep-research-search 用 3456，各自独立进程、独立端口，共享同一个 Chrome 实例（都连 9222）。两套 proxy 可并存，互不抢占端口、互不干扰会话。
- **理由**：
  - deep-research-search 失败模式#10："CDP Proxy 被误判为应替换 → MCP 实测慢且掉线，CDP Proxy 操作模式更优"
  - MCP 工具每次调用经 MCP 协议封装，高并发下掉线；CDP Proxy 是 localhost HTTP，bash 脚本化批处理稳定
  - 直连用户日常 Chrome 天然携带登录态，无需独立浏览器实例
- **代价**：需用户开启 Chrome remote-debugging（check-deps.mjs 引导）

### D2：为何从 deep-research-search 移植脚本而非 web-access

- **决策**：cdp-proxy.mjs / cdp_client.py / human_behavior.py / check-deps.mjs 从 deep-research-search 移植
- **理由**：
  - web-access 工程过时（用户明确指示"web-access 是过时的工程"）
  - deep-research-search 的 cdp_client 是防腐层 ACL（隔离 proxy 协议变更），human_behavior 是实战验证的拟人引擎，是现代实践
  - deep-research-search 自包含（不依赖 web-access 脚本），移植不破坏它
- **代价**：脚本有两份副本（deep-research-search + web-chrome），后续维护需同步

### D3：为何 11 主动淘汰而非 15 才淘汰

- **决策**：两层阈值——11 整理线（主动淘汰触发）+ 15 硬上限（兜底）
- **理由**：
  - 留 4 个安全余量，避免边缘状态下（并发子 agent 同时开 tab）无 tab 可用
  - 11 时就开始整理，给 LLM 评分淘汰留决策空间，不至于到 15 才仓促处理
  - cdp-proxy.mjs 在 15 兜底返回 429，是最后一道防线

### D4：为何智能淘汰（LLM 评分）而非 LRU

- **决策**：达整理线时，LLM 按 5 维度评分选最低分者淘汰（用户明确要求"按任务价值智能淘汰"）
- **理由**：
  - 任务语义价值比访问时间更重要——已读完的核心来源（LRU 会淘汰）比刚访问的跑题页更该保留
  - 5 维度（信息完整度/任务相关性/重访成本/新鲜度/独特性）覆盖了"该不该留"的核心判断
- **代价**：需 LLM 介入做评分（成本），但只在达整理线时触发，频率可控

### D5：为何 isTrusted 是第一档硬规则

- **决策**：所有拟人交互必须走 CDP Input（isTrusted=true），禁用 JS dispatchEvent
- **理由**：
  - deep-research-search human_behavior.py 文档明确："不经过 JS dispatchEvent（后者 isTrusted=false，反爬一查即穿）"
  - 这是反爬的底层物理事实，非策略选择，故列为不可违反的第一档规则

### D6：为何拦截检测是独立脚本而非内嵌

- **决策**：intercept_detector.py 独立，agent 在关键节点主动调用 `check`
- **理由**：
  - 6 类信号（CAPTCHA/HTTP_BLOCK/EMPTY_SERP/LOGIN_WALL/CONTENT_GONE/FINGERPRINT）需综合 title+body+html+url+操作历史判断，逻辑复杂，独立脚本可维护
  - agent 决定何时检测（操作后/异常时），避免每步都检测的开销
- **代价**：依赖 agent 主动调用，可能漏检——通过规则6（拦截必须记录）和规则8（失败2次重评估）缓解

## 失败模式（随执行反馈填充）

> 此区是 skill 自我演进的记忆入口。每遇到未覆盖的失败，记录现象+根因+修正。

| # | 失败现象 | 根因 | 修正 |
|---|---------|------|------|
| F1 | （待填充） | | |

## V1 工程基线

- 脚本移植自 deep-research-search（cdp-proxy.mjs / cdp_client.py / human_behavior.py / check-deps.mjs）
- TAB_POOL_LIMIT: 30 → 15（cdp-proxy.mjs + cdp_client.py 同步调整）
- 新增 tab_manager.py（页面池 + 智能淘汰编排）
- 新增 intercept_detector.py（6 类拦截信号识别）
- 新增 site-patterns/ 经验目录（扩展 web-access 格式，新增"反爬规避"区）

## 待办 / 已知局限

- [ ] site-patterns/ 初始为空，需通过实际操作积累首批经验
- [ ] 拦截检测依赖 agent 主动调用，未来可考虑在 acquire/eval 后自动检测（权衡开销）
- [ ] tab 状态文件 `~/.web-chrome-tabs.json` 是单机单用户设计，多 agent 并发写可能有竞争（当前用 json 原子写缓解）
