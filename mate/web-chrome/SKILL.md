---
name: web-chrome
description: "为 agent 提供自动化通过 chrom 浏览器上网能力。需要浏览或打开网页、获取或抓取内容、操作页面及登录态网站时触发；多轮深度调研不触发。"
version: "1.0"

---

# web-chrome：agent 的眼睛和手

## 思考方式

浏览器是研究者的书桌，不是无底的回收站。

书桌上同时摊开的书有上限——不是物理限制，而是认知限制。摊开 15 本书时你已经在顾此失彼。当书桌开始拥挤（第 11 本），你不是随机收起一本，而是收起**对当前任务最没用的那本**：已经读完的、跑题的、重复的。这就是智能淘汰——它尊重任务的语义，而不是机械的访问时间。

每访问一个新站点，你都在积累经验：这个站点的脾气、什么操作有效、什么会触发警报。**被拦截不是失败，而是最珍贵的学习时刻**——它告诉你站点的防御边界在哪。记录下来，下次绕开。

两条贯穿性原则：

- **像人一样浏览，兼顾高效与适应**：能程序化就程序化（快），遇阻碍就 GUI 化（稳）。所有"必须像人"的交互走 CDP Input（isTrusted=true），不走 JS dispatchEvent（isTrusted=false，反爬一查即穿）。
- **LLM 判断价值，脚本管理机制**：哪个 tab 该关由 LLM 评（语义判断），池子的计数/淘汰执行由脚本做（机械可靠）。

## 工具决策

| 场景 | 工具 |
|------|------|
| URL 已知，要原始 HTML（meta、JSON-LD） | curl |
| 反爬平台 / 登录态 / JS 渲染 / 自由导航探索 | **CDP Proxy（本 skill 核心）** |
| PDF 等二进制下载 | curl |

CDP Proxy 不要求 URL 已知——可从任意入口出发，通过页面内点击、跳转找到目标。进入浏览器层后，`/eval` 是你的眼睛（查 DOM）和手（操作元素）。

## 端到端流程

```
前置检查
  node check-deps.mjs（Node + Chrome CDP + Proxy）
  │  向用户展示风控提示后继续
  ▼
读站点经验                          ← Read references/experience.md
  site-patterns/{domain}.md 存在则先读
  │
  ▼
开 tab（页面池管理）                 ← Read references/tab-pool.md
  tab_manager.py acquire（达 11 先淘汰）
  │
  ▼
拟人浏览 / 程序化提取                ← Read references/human-browse.md
  已知反爬 → 直接 GUI 拟人
  未知 → 程序化探测，受阻降级 GUI
  │
  ▼
拦截检测（关键节点 / 异常时）        intercept_detector.py check
  检测到 → 停止 → 写经验 → 降级策略
  │
  ▼
提取内容 / 完成任务
  │
  ▼
写站点经验（成功 / 拦截后）          ← references/experience.md
  site-patterns/{domain}.md 追加（标注日期）
  │
  ▼
关 tab（任务完成或淘汰）
```

## 初始化

```bash
# 1. 环境检查（Node ≥ 22 + Chrome CDP 连通性 + Python requests）
node ${CLAUDE_SKILL_DIR}/scripts/check-deps.mjs

# 2. 风险提示（必须向用户展示后再操作）
```
> 温馨提示：部分站点对浏览器自动化操作检测严格，存在账号封禁风险。已内置防护措施但无法完全避免，Agent 继续操作即视为接受。
```

## 页面池

15-tab 智能页面池：**11 主动整理线 + 15 硬上限**。

- 管理的 tab 达 11 时，开新 tab 前必须先淘汰一个（`tab_manager.py acquire` 会拒绝并提示）
- LLM 按 5 维度评分（信息完整度/任务相关性/重访成本/新鲜度/独特性），选最低分者淘汰
- pinned tab 免淘汰；用户已有的 tab 绝不纳入管理

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py status     # 池健康度
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py acquire URL --task "标签"
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py list       # 达整理线时输出元数据供评分
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py evict ID   # 淘汰 LLM 选定的最低分者
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py pin ID     # 标记关键 tab
```

## CDP Proxy 核心 API

```bash
# 列出所有 tab（操作前必须快照，区分用户 tab 和本 skill tab）
curl -s http://localhost:3457/targets

# 创建后台 tab（TabPool 保护，达 15 返回 429）
curl -s "http://localhost:3457/new?url=URL"

# 页面信息
curl -s "http://localhost:3457/info?target=ID"

# 执行 JS（纯 DOM 读取）
curl -s -X POST "http://localhost:3457/eval?target=ID" -d 'document.title'

# 导航 / 后退
curl -s "http://localhost:3457/navigate?target=ID&url=URL"

# 拟人鼠标（isTrusted=true，走 CDP Input）
curl -s -X POST "http://localhost:3457/input/click?target=ID" -H 'Content-Type: application/json' -d '{"x":400,"y":300}'
curl -s "http://localhost:3457/input/scroll?target=ID&direction=down&y=3000"

# 截图（含视频当前帧）
curl -s "http://localhost:3457/screenshot?target=ID&file=/tmp/shot.png"

# 关闭 tab
curl -s "http://localhost:3457/close?target=ID"
```

复杂拟人交互（贝塞尔鼠标轨迹、泊松停顿、随机落点）用 Python：
```python
from human_behavior import HumanBehavior
from cdp_client import CdpClient
human = HumanBehavior(CdpClient())
human.click_selector(target_id, 'button.load-more')  # 人类点击 CSS 选择器
human.human_scroll(target_id, 'down', 2400)          # 人类滚动
```

## 规则

### 第一档：操作安全（不可违反）

违反会导致功能故障或封号风险：

1. **操作前必须 `/targets` 快照**——只关本 skill 创建的 tab，绝不误关用户 tab
2. **只用工具决策表中的工具**——不引入未定义的工具
3. **页面池达 11 时必须先淘汰再开新 tab**——15 是硬上限，cdp-proxy 在此层兜底拒绝
4. **拟人交互必须走 CDP Input（isTrusted=true）**——禁用 JS dispatchEvent / el.click()（isTrusted=false，反爬一查即穿）
5. **拦截发生时必须停止 + 记录**——不反复撞墙，写入站点经验后选择降级策略

### 第二档：结构保障（规则 + 反思）

违反会导致质量问题：

6. **访问站点前先查 site-patterns 经验**
   → 这个站点你以前踩过坑吗？经验文件里记的规避策略还在有效期内吗？
7. **每个 tab 开启时标注 task 标签**
   → 如果说不清这个 tab 服务于什么任务，你可能正在无目的地摊开书桌
8. **程序化受阻时降级 GUI 拟人**
   → 你是在发现信息还是在重复撞墙？同一方式失败 2 次就该重新评估方向

### 第三档：浏览质量（反思性引导）

遵守了形式但没遵守精神就没意义：

9. **像人一样浏览，还是像机器人一样抓取？**
   → 你的操作节奏有没有规律可循？高频精确点击比低频随机点击更像机器人
10. **被拦截时，这次失败能帮下次成功吗？**
   → 你记录的触发条件够具体吗（什么操作、什么频率、什么症状），还是只写了"被拦了"？

## 迭代协议

用户带执行反馈 / 拦截案例回来时，读取 `references/design-rationale.md` 理解原有设计，定位失效点（对照失败模式表 F#），针对性修正并补充经验。

## References 索引

| 文件 | 何时加载 |
|------|---------|
| `references/tab-pool.md` | 开 tab / 淘汰 tab 时（5 维度评分维度） |
| `references/experience.md` | 访问新站点前 + 操作成功/被拦截后（经验格式 + 读前写后协议） |
| `references/human-browse.md` | 需要拟人交互（点击/滚动/翻页）时（GUI vs 程序化决策） |
| `references/design-rationale.md` | 遇到未覆盖的失败 / 用户带反馈时（设计决策 + 失败模式） |
