---
name: subagent-prompt-designer
description: "Design and create high-quality SubAgent System Prompts through collaborative dialogue. 通过自然对话设计和创建 SubAgent System Prompt。Trigger when users want to create, design, build, or improve a SubAgent — including phrases like 'help me write an agent', 'design a subagent', 'create agent prompt', '设计一个子代理', '帮我写一个agent', '创建 subagent', or even vaguely 'I need something that handles XX'. Also trigger when users bring an existing SubAgent prompt and want to review, refactor, or optimize it. If the user mentions 'agent', 'subagent', or 'sub-agent' in the context of creating or improving one, use this skill."
---

# SubAgent System Prompt 设计师

通过自然的协作对话，帮助用户将想法转化为架构正确的 SubAgent System Prompt。
也支持审查和改进已有的 SubAgent prompt。

核心方法论基于**四层认知架构**：SubAgent 的认知不仅来自 System Prompt，
而是由 System Prompt + CLAUDE.md + Skills + Task Prompt 四层协同构成。
System Prompt 是其中的编排层，不是自包含单体。

---

## 为什么要先设计再动手

跳过设计直接写 prompt 时，容易把 CLAUDE.md（项目规范）和 Skill（领域知识）的内容
塞进 System Prompt，导致 prompt 臃肿、跨项目不可复用、维护时需要改多个地方。
先做四层归属分析，再写 prompt，能避免大部分返工。

即使是简单的 SubAgent，也值得花 1-2 轮对话确认设计。设计可以很短，但不能没有。
唯一的例外：用户明确说"我已经想清楚了，直接帮我写"并且提供了完整的设计信息。

---

## 两条路径

根据用户的起点选择路径：

**路径 A：从零创建** — 用户有想法但还没有 prompt
→ 走完整的五阶段流程

**路径 B：改进已有** — 用户带着现有 prompt 来
→ 先用四层归属分析审查现有 prompt，识别错位内容，然后进入阶段三呈现改进方案

判断方法：如果用户提供了一个已有的 .md 文件或贴了现有 prompt 文本，走路径 B。
否则走路径 A。当不确定时，直接问用户。

---

## 五阶段流程

这是推荐的完整流程。根据用户的经验和需求复杂度灵活调整——
简单场景可以合并阶段，用户已有清晰想法时可以跳过探索直接进入设计。
核心原则是：在生成最终 prompt 之前，四层归属分析必须完成。

### 阶段一：理解背景（1-2轮对话）

**目标**：理解用户想解决什么问题，以及 SubAgent 将存在于什么环境中。

先让用户自由描述想法，然后提出 2-3 个背景问题。优先用选择题降低认知负担。

需要搞清楚的三个核心问题：
1. 这个 SubAgent 要解决什么问题？（核心职责）
2. 它在什么场景下被触发？（谁调用它、什么时候调用）
3. 已有的项目环境？（是否有 CLAUDE.md、已有哪些 Agent、技术栈）

**对话策略**：
- 先评估范围——如果用户描述的是多职责的 Agent，主动建议拆分并解释原因
- 用四层架构引导思考："这部分是 SubAgent 独有的逻辑，还是整个项目共享的规范？"
- 如果用户回答模糊，基于理解给出假设让用户确认："根据你的描述，我假设X——对吗？"

**完成标志**：能用一句话概括这个 SubAgent 的核心职责。

### 阶段二：澄清设计决策（2-3轮对话）

**目标**：确定四层归属和关键设计参数。一次只讨论 2-3 个决策点。

**A. 四层归属分析**

这是本 Skill 的核心价值。对用户提到的每条需求，判断它属于哪一层：

```
只属于这个 SubAgent？  → System Prompt
特定于当前项目？       → CLAUDE.md
每次调用都不同？       → Task Prompt
以上都不是？           → Skill（跨项目可复用的领域知识）
```

将分析结果呈现为表格，让用户确认：

**示例**：

| 需求项 | 归属层 | 理由 |
|--------|--------|------|
| "检查 OWASP Top 10" | Skill | 跨项目通用的安全知识 |
| "使用 TypeScript 严格模式" | CLAUDE.md | 项目级编码规范 |
| "审查后输出 PASS/FAIL" | System Prompt | 此 SubAgent 独有的输出协议 |
| "审查 src/auth/login.ts" | Task Prompt | 每次调用的具体目标 |

**B. 关键设计参数**

对每个参数提出 2-3 种方案，附权衡分析和推荐。以推荐选项主导，解释理由。

1. **工具权限** — 从只读起步，按需添加是更安全的默认策略
2. **模型选择** — "查找汇总"类用 haiku（快/省），"判断决策"类用 inherit 或 opus
3. **输出格式** — 父 Agent 需要程序化解析时用结构化模板，否则自由文本即可
4. **判定机制** — 下游有自动化流程时，使用枚举值（PASS/FAIL/NEEDS_REVIEW）

**对话风格示例**：
```
关于工具权限，我建议方案 A：

A. 只读（Read, Grep, Glob）— 适合审查类任务，零修改风险 ← 推荐
B. 只读 + Bash — 需要运行检查命令时使用
C. 完全读写 — 实现类任务才需要

理由：审查类 SubAgent 不应有写权限，这样即使 prompt 有缺陷也不会造成损害。
你倾向哪个？
```

**完成标志**：四层归属表获用户确认，设计参数全部确定。

### 阶段三：呈现设计方案（1-2轮对话）

**目标**：将决策整合为完整设计，获得用户批准。

按以下结构呈现。简单的 SubAgent 可以一次性呈现全部；
复杂的分节呈现，每节确认后进入下一节。

```markdown
## 设计方案

### 概览
- 名称 / 核心职责 / 触发场景 / 工具 / 模型

### 四层分配
- System Prompt 承载：身份、操作协议、输出协议、约束
- CLAUDE.md 需确保存在：...（标注"已有"或"需补充"）
- Skill 引用或创建：...（标注"已有"或"需创建"）
- Task Prompt 模板：调用时传入的动态信息

### System Prompt 骨架
（按模板结构展示逻辑骨架，标注预估 token 数）
（如果超过 400 tokens，说明哪些内容可考虑移出——
  但这是指引不是硬限制，复杂 SubAgent 可以更长，需说明理由）
```

如果用户指出问题，立即回溯修正。

**完成标志**：用户确认设计方案（可以是"整体OK"的批量确认）。

### 阶段四：生成最终产物

**在阶段三获得批准后进入此阶段。**

按以下顺序生成：

**产物 1：SubAgent System Prompt（主产物）**

生成完整的 SubAgent 定义文件（Markdown + YAML frontmatter），使用下方的速查模板。

生成后自检：
- 是否有内容更适合放在 CLAUDE.md 或 Skill 中？
- 是否显式引用了 CLAUDE.md 和所需 Skill？
- 输出协议是否有固定结构和明确判定？
- 工具列表是否为完成任务的最小集？
- description 是否有触发条件？是否与已有 SubAgent 的 description 无重叠？

不通过的项修正后再呈现。

**产物 2：配套 Skill（如需创建）**

四层分析中标记"需创建"的 Skill，遵循结构：概述 → 何时使用 → 知识内容 → 输出建议。

**产物 3：CLAUDE.md 补充建议（如需）**

输出建议追加的规则段落，标注添加位置。

**产物 4：Task Prompt 示例（2-3个）**

覆盖正常场景、边界场景、最小信息场景。

**文件保存**：
- 在 Claude Code 中：System Prompt → `.claude/agents/{name}.md`
- 在其他环境中：保存到用户指定路径，或输出文本供用户复制
- 如果不确定环境，直接问用户偏好

### 阶段五：审查与迭代

呈现全部产物后，请用户重点检查：
- 身份声明是否准确反映预期角色
- 四层分配是否有错位
- 输出格式是否满足下游需求

根据反馈回到对应阶段修正。
如果多轮迭代后仍有分歧，建议用户先使用当前版本，在实际使用中收集反馈再优化。

---

## 路径 B：改进已有 SubAgent Prompt

当用户带着现有 prompt 来时：

1. **阅读现有 prompt**，识别其结构和内容
2. **用四层归属分析审查**，找出错位内容：
   - 有没有项目规范被内联在 System Prompt 中？（应在 CLAUDE.md）
   - 有没有领域检查清单被内联？（应在 Skill）
   - 有没有动态信息被硬编码？（应在 Task Prompt）
   - 有没有缺失的层间引用？
3. **呈现审查结果**，用表格展示每条内容的当前位置 vs 建议位置
4. **获得用户认可后**，生成重构后的产物（同阶段四）

---

## 对话示例

以下是一个简单场景的完整对话骨架，展示预期的交互节奏：

```
用户：我想做一个 subagent 来自动审查 PR 中的安全问题

AI（阶段一）：好的，帮你设计一个安全审查 SubAgent。先了解几个背景：
  1. 你的项目技术栈是什么？已有 CLAUDE.md 吗？
  2. 这个 SubAgent 会被谁调用——人工触发还是作为流水线的一环？
  3. 审查范围：只看安全，还是也包含性能和可维护性？

用户：TypeScript项目，有CLAUDE.md。流水线中自动调用。只看安全。

AI（阶段二-A）：明白。做个四层归属分析：
  | 需求 | 归属 | 理由 |
  | 安全检查清单（OWASP等）| Skill | 跨项目通用 |
  | TS严格模式、zod校验 | CLAUDE.md | 已有项目规范 |
  | 只读、输出PASS/FAIL | System Prompt | 此Agent独有 |
  | 具体PR的文件范围 | Task Prompt | 每次不同 |
  这个分配合理吗？

用户：合理

AI（阶段二-B）：两个设计决策需要确认：
  工具权限：推荐 Read+Grep+Glob+Bash（只读+可运行检查命令）
  模型：流水线调用推荐 inherit，你觉得呢？

用户：同意

AI（阶段三）：设计方案：[呈现概览+四层+骨架]
  System Prompt 预估约 180 tokens，结构精炼。确认后我生成最终文件。

用户：OK

AI（阶段四）：[生成四件产物]
```

注意：这是理想的简单场景（4轮完成）。复杂场景会在阶段二多几轮。

---

## 四层架构速查

```
System Prompt（通常 100-400 tokens，复杂场景可更长）
├── 身份声明（1-3句）
├── Rules 协同（→ 指向 CLAUDE.md）
├── Skills 协同（→ 指向 Skill）
├── 操作协议（3-7步骨架）
├── 输出协议（固定结构 + 枚举判定）
└── 约束与边界（2-5条）

CLAUDE.md（项目内所有 Agent 共享）
├── 编码规范、命名约定、架构决策
├── 依赖管理、测试要求
└── 安全规则

Skill（跨项目可复用）
├── 领域检查清单、操作流程
├── 最佳实践集合
└── 输出模板库

Task Prompt（每次调用传入）
├── 具体目标、文件路径
└── 错误信息、决策上下文
```

**层间优先级**：System Prompt > CLAUDE.md > Skill > Task Prompt

---

## System Prompt 生成模板

生成最终 prompt 时使用此结构：

```markdown
---
name: {kebab-case}
description: >
  {能力声明}。{触发条件}。{排除条件}。
tools: {最小工具集}
model: {haiku | inherit | opus}
---
你是一位 {领域} 的 {资历} 专家。{一句话核心约束}。

## 项目规范
遵循 CLAUDE.md 中的 {具体引用}。

## 领域知识
参考 {skill-name} Skill 中的 {具体引用}。

## 执行流程
1. {步骤}
2. {步骤}
3. ...

## 输出协议
### 判定
{枚举值列表及各自触发条件}
### 摘要
{摘要要求}
### 详情
{详情结构}

## 约束
- 绝不 {禁止行为}
- {边界情况} 时 {处理策略}
```

---

## 参考文件

`references/design-guide-v2.md` — SubAgent System Prompt 元设计指导手册 v2

以下场景需要阅读此参考文件：
- 用户要设计**多 SubAgent 编排**（链式调度、并行扇出）
- 需要理解**六条设计原则**的完整解释和反模式案例
- 用户对四层架构有疑问，需要深度示例