---
name: st-notes
description: 用户想“把学习结果整理成笔记、生成概念笔记、沉淀我的表述、做 Obsidian 笔记、为某个 source/concept/all 产出学习笔记”时使用。它从 st-study 的会话日志和 learner model 中提取用户原话，生成带“何时用得上”锚点的 Markdown 笔记。
argument-hint: "[source-id | concept-name | all]"
disable-model-invocation: true
allowed-tools: Read, Write, Glob, Grep
---

# st-notes — 学习笔记产出

把学习会话中用户真正说出来的东西沉淀成笔记。笔记的核心不是“标准答案”，而是用户将来能想起、能迁移、能继续生长的个人理解。

## 边界

`st-notes` 只产出笔记和回写笔记路径，不学习新概念，不评估回答，不修改 mastery。

笔记材料优先级：

1. 用户在 `st-study` 中的原始表述。
2. 用户的总结句。
3. 用户确认过的跨域映射。
4. extraction 中的标准内容，只作为补充，并明确标注来源。

AI 新生成的解释不能冒充用户理解。未被用户确认的 AI 连接，不写入“跨域映射”，最多写入“待确认”。

## 输入

- `{source-id}`：为指定来源下符合条件的概念生成笔记。
- `{concept-name}`：为单个概念生成笔记。
- `all`：为所有 `mastery >= 2` 且尚未生成笔记的概念生成。

## 前置检查

1. 读取 `learning/learner/model.json`。
2. 读取 `learning/learner/sessions/*.md`。
3. 读取相关 `learning/extractions/*.md`。
4. 读取本 skill 的参考文件：`references/note-format.md`。
5. 确认或创建 `learning/notes/`。

如果没有会话日志，仍可用 extraction 生成“标准笔记草稿”，但必须明确告诉用户：缺少学习者原始表述，这不是个人化笔记。

## 笔记生成条件

默认只为 `mastery >= 2` 的概念生成笔记，因为至少要有一次用户能解释核心机制。

例外：

- 用户明确要求为未完成概念生成草稿。
- 该概念有足够的用户原话，但 model 中状态未同步。

遇到例外时，在笔记 frontmatter 中标注 `status: draft`。

## 收集材料

对每个目标概念，收集：

- `model.json` 中的 `learner_outputs`。
- `sessions/*.md` 中该概念下的学习者表述、总结句、误解记录和跨域映射。
- extraction 中的简化层、精度层、拓展层。
- profile 中已确认的相关认知桥梁。

如果用户表述和 extraction 冲突，不要悄悄修正。保留用户原话，并在“精度补充”中说明标准内容如何校正。

查找和回写时以 `concept_id` 为准；概念名只用于展示。不要因为概念名微调就创建第二条 model 记录或第二篇重复笔记。

## 笔记格式

写入 `learning/notes/{concept-slug}.md`：

```markdown
---
concept: {概念名}
source: {来源标题}
source_id: {source-id}
concept_id: {source-id}--{concept-slug}
mastery: {当前级别}
status: {complete|draft}
created: YYYY-MM-DD
updated: YYYY-MM-DD
related:
  - "[[{相关概念}]]"
---

# {概念名}

> {用户总结句；如果没有，写“暂无用户总结句”}

## 核心理解

{以用户原话为主，必要时轻微整理语序，但不要改写思想。}

> **[来源补充]** {extraction 中补足核心结构的内容}

## 精度补充

{简化版遮掉的内容，以及这些内容会在什么场景改变判断。}

## 何时用得上

- {场景型/问题型/概念型锚点，至少一个}

## 跨域映射

- {用户提出或确认过的结构同构}

## 易错点

- {来自 misconceptions 或学习过程中暴露的偏差}
```

## 锚点要求

每篇笔记必须有“何时用得上”。锚点可以是：

- 场景型：当你遇到某种现实问题时会想起它。
- 问题型：当你追问某个长期问题时，它给一个判断框架。
- 概念型：它和你已理解的某个概念共享同一骨架。

锚点要具体。不要写“用于理解经济学”“用于学习 AI”这种空泛句子。

## 合并已有笔记

如果笔记已存在：

- 用户最新表述优先，但旧表述不要直接删除；可移入“历史表述”或保留更有洞察的句子。
- 精度补充保留更完整版本。
- 已确认跨域映射只增不减。
- `updated` 改为今天。

不要覆盖用户手动补过的内容。遇到明显人工扩写，保留并在末尾追加新内容。

## 回写 model

生成或更新笔记后，在 `model.json` 对应概念中写入：

```json
{
  "learner_notes_path": "learning/notes/{concept-slug}.md"
}
```

按 `concept_id` 找到对应概念后合并字段，保留其他字段。

## 输出摘要

```text
━━ 笔记生成报告 ━━
生成/更新笔记: {N} 篇
位置: learning/notes/

笔记列表:
- {概念名}: mastery {级别} | 锚点: {锚点摘要}

建议下一步:
- 用 /st-connect 发现跨概念连接
- 用 /st-review 做间隔复习
```

## Obsidian 集成

笔记使用 Markdown 和 `[[wiki-link]]`。当前系统默认写入 `learning/notes/`，如果要进入主知识库，可移动到本 vault 的 `02知识库/` 下合适主题目录。移动后如需系统继续追踪，更新 `model.json` 中的 `learner_notes_path`。
