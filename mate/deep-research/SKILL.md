---
name: deep-research
description: 对在线网页或本地资料执行可追溯的深度调研，形成带引用、反方证据、置信度和质量校验的研究报告。用于用户要求深度调研，或开展行业、公司、产品、技术、政策、趋势、竞品研究及研究备忘录；在线模式必须与 $web-chrome 协作。简单单事实查询不使用。
---

# Deep Research

把研究目标转换为一组可验证的问题，通过浏览器实地取证或本地资料审阅建立证据账本，再生成可追溯、可复核的报告。

## 能力边界

- 本 skill 负责研究设计、问题分解、证据覆盖、冲突处理、综合判断和报告质检。
- `$web-chrome` 负责搜索与网页访问、登录态、反爬处理、页面提取和标签页生命周期。
- `scripts/` 只负责确定性工作：目录初始化、证据校验与去重、数据池导出、报告组装和机械质检。
- 不自建第二套浏览器控制、搜索代理或无头抓取服务。
- 搜索结果摘要只用于发现候选来源，不能直接作为报告证据。
- 不自动安装依赖、不自动更新 skill、不删除旧报告。

## 启动规则

1. 从用户请求中识别研究对象、决策用途、时间范围、地域范围、交付语言和期望深度。
2. 只有会显著改变研究结论的歧义才向用户确认；其余采用明确、可撤销的假设继续。
3. 读取 [profiles.json](profiles.json)，选择 `quick`、`standard` 或 `deep`：
   - `quick`：方向扫描、会前准备、低风险判断。
   - `standard`：默认；需要跨来源验证的完整研究。
   - `deep`：高风险决策、争议主题或要求系统穷尽。
4. 在线研究先加载 `$web-chrome` 并遵守 [references/web-chrome-contract.md](references/web-chrome-contract.md)。离线研究只处理用户提供的本地文件。
5. 用 `scripts/init_workspace.py` 在项目的 `works/tmp/` 下建立本任务独立临时目录；关键词不超过 6 个字符。最终产物默认写入 `works/research/`，不得把中间文件散落到仓库根目录。

## 工作流

### 阶段一：定义研究问题

将主题转换成一个可判定的主问题和若干子问题。每个子问题必须有：

- 稳定的 `id`
- `priority`：`high`、`medium` 或 `low`
- 需要的证据类型与首选来源角色
- 可证伪条件或应寻找的反方证据

按 [references/outline-prompt.md](references/outline-prompt.md) 写入 `outline.json`。先回答“这项研究要支持什么决定”，再决定搜什么。

### 阶段二：制定来源策略

按主张类型选来源，不做无目的的“全网撒网”。优先顺序通常为：

1. 一手材料：法规、官方数据、公司披露、产品文档、论文原文、判决或标准。
2. 独立专业材料：同行评审、权威数据库、专业媒体、分析机构。
3. 相关方观点：公司、专家、用户、社区或反对者，用于解释立场而非替代事实。

具体规则见 [references/source-strategy.md](references/source-strategy.md)。

### 阶段三：通过浏览器取证

在线模式由 `$web-chrome` 执行网页操作。每次提取至少记录：

- 页面标题、规范化 URL、发布者、发布日期和访问时间
- 提取方式与页面定位信息
- 与哪个研究问题相关
- 可核验的短摘录或数据上下文
- 主张类型、时间属性、置信度及其理由

把证据逐条写入 JSONL 账本，不保存整页正文作为默认产物。账本结构见 [references/evidence-schema.md](references/evidence-schema.md)。

遇到登录、验证码、访问限制或动态页面时，按 `$web-chrome` 的降级链处理。确认被拦截后停止重复同类尝试，记录证据缺口并继续其他问题。

### 阶段四：覆盖检查与补充轮次

每轮结束都计算三个信号：

- `coverage`：高优先级问题是否有足够独立证据。
- `convergence`：新增来源是否仍在改变核心判断。
- `novelty`：最近一轮新增来源带来的新主张比例。

达到配置中的最大轮次必须停止。若核心问题已覆盖、结论趋于稳定且新信息很少，可提前停止。来源数量是预算和预期，不是凑数指标。

补充检索只针对：

- 高优先级问题的证据空白
- 关键数字缺少时间、单位、口径或原始出处
- 来源之间的直接冲突
- 主结论缺少反方或边界条件

详细循环见 [references/research-workflow.md](references/research-workflow.md)。

### 阶段五：综合与写作

先从证据账本导出 `data-pool.json` 和 `manifest.json`，再写章节。报告必须区分：

- 已验证事实
- 估算或预测
- 来源观点
- 基于证据的推断
- 尚未解决的空白

不得把来源没有直接支持的因果关系写成事实。相互冲突的数据要并列呈现，并解释口径、时间或利益立场差异。

正文使用数字引用 `[N]`，每个引用必须能回到具体 URL、本地文件或定位信息。标准见 [references/report-standard.md](references/report-standard.md)。

### 阶段六：质量校验

按顺序执行：

1. JSON 与 UTF-8 校验。
2. 数据池字段、证据缺口和高优先级覆盖校验。
3. 章节结构、长度与深度平衡校验。
4. 报告引用、来源清单、时间锚点和免责声明校验。
5. 人工语义复核：引用是否真的支持相邻主张，反方证据是否被公平处理，结论是否超出证据。

机械检查通过不代表研究必然正确；最终回复要明确说明仍存在的限制。

## 进度沟通

长任务在每个研究轮次结束后向用户更新一次，内容只包括：已完成的问题、当前覆盖、主要缺口和下一步。不要暴露内部推理草稿。

只有用户明确要求且运行环境允许时才使用子代理；否则在当前代理内完成。任何并发都必须遵守项目 `AGENTS.md` 的并发上限。

## 产物

一次完整研究应保留：

```text
works/tmp/<任务目录>/
├── .deep-research.json
├── outline.json
├── evidence.jsonl
├── data-pool.json
├── manifest.json
├── raw/
├── notes/
├── chapters/
└── records/

works/research/<研究目录>/
├── report.md
├── evidence.jsonl
└── manifest.json
```

若用户只要简短答案，可以缩短报告，但仍保留临时证据账本与来源定位。

## 参考路由

- 研究轮次、停止条件、异常恢复：读取 [references/research-workflow.md](references/research-workflow.md)
- 浏览器职责、标签页和拦截处理：读取 [references/web-chrome-contract.md](references/web-chrome-contract.md)
- 证据记录、字段和引用映射：读取 [references/evidence-schema.md](references/evidence-schema.md)
- 查询与来源选择：读取 [references/source-strategy.md](references/source-strategy.md)
- 研究大纲格式：读取 [references/outline-prompt.md](references/outline-prompt.md)
- 报告结构与语义质检：读取 [references/report-standard.md](references/report-standard.md)

