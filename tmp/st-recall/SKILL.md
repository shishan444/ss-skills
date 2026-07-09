---
name: st-recall
description: 用户想“自测、抽题、检查自己还记不记得、随机问我几个、测试某个概念/来源”时使用。它从 learning/questions 和 learner model 中抽开放题，评估回答并更新复习参数；不讲新课，不提升 mastery。
argument-hint: "[source-id | concept-name | random]"
disable-model-invocation: true
allowed-tools: Read, Write, Glob, Grep
---

# st-recall — 主动召回自测

从题库中抽开放式问题，测试学习者是否还能主动取回概念结构。它的价值不是判分，而是暴露“以为懂了但取不出来”的地方。

## 边界

`st-recall` 不学习新概念，不推进 mastery。它只更新：

- `attempts`
- `correct_count`
- `last_review`
- `easiness`
- `interval_days`
- `next_review`
- `misconceptions`

如果用户明显没学过这个概念，引导去 `/st-study {source-id}`。

## 输入

- `{source-id}`：测试指定来源下已学过的概念。
- `{concept-name}`：测试指定概念。
- `random` 或留空：从已学概念中抽样。

## 前置检查

1. 读取 `learning/learner/model.json`。不存在时提示先运行 `/st-study`。
2. 读取 `learning/questions/*.json`。
3. 读取相关 `learning/extractions/*.md`，用于评估回答。
4. 采用本文件的评估规则；需要更细时，保持和 `st-study` 的“核心结构、自主表述、边界/迁移意识”三维标准一致。

## 选题规则

### 按 source-id

1. 读取 `learning/questions/{source-id}.json`。
2. 在 model 中筛选该来源下 `mastery >= 1` 的概念。
3. 每个概念最多抽 1 题，避免一次自测过长。

### 按概念名

1. 在 model 和 questions 中模糊匹配概念名。
2. 如果匹配多个，列出候选让用户选择。
3. 抽取该概念当前 mastery 对应难度的题。

### random

1. 从所有 `mastery >= 2` 的概念中抽最多 5 个。
2. 优先选择：
   - 最近没复习过的。
   - `easiness` 低的。
   - 有 misconceptions 的。

## 难度映射

- `mastery 1`：优先 `L1_identify`，确认是否认识。
- `mastery 2`：优先 `L2_explain`，测试能否解释核心机制。
- `mastery 3`：优先 `L2_explain` 或精度边界问题。
- `mastery 4`：优先 `L3_transfer`，测试迁移能力。

找不到对应难度题目时，可以临时根据 extraction 生成一个开放题，并在报告里标注“临时题”。

## 测试流程

对每道题：

1. 呈现题目：

```text
━━ 题目 {N}/{总数} ━━
{题目文本}
```

2. 等待学习者回答。不要替用户回答。
3. 对照 extraction 和题目的 `must_include` 或 `transfer_signal` 评估。
4. 给出反馈：

```text
{通过/部分通过/不通过}
- 你抓住了: {具体内容}
- 遗漏/偏差: {具体内容}
- 核心提示: {一句话}
```

反馈必须具体引用学习者的原话或遗漏点，不要只说“不错”“不够完整”。

## 评估规则

- 通过：核心结构完整，关系正确，并且是自己的表达。
- 部分通过：抓住主干，但漏掉 1-2 个关键要素或边界。
- 不通过：核心机制错、概念混淆、只背词但解释不出关系。

质量分数：

- `5`：一次通过，且表达有迁移或边界意识。
- `4`：一次通过，有小瑕疵。
- `3`：部分通过，提示后能补上。
- `2`：不通过，但重讲后能接近。
- `1`：多次不通过。
- `0`：完全无法取回。

## 更新复习参数

每题后更新 `model.json`；如果该概念已在 `learning/schedule.json` 中，也同步更新 schedule。

简化 SM-2。`st-recall` 和 `st-review` 使用同一套规则：

```text
easiness_new = easiness + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
easiness_new 限制在 [1.3, 3.0]

q >= 3:
  interval_new = 6 if interval_days <= 1 or review_count == 0 else round(interval_days * easiness_new)
q < 3:
  interval_new = 1
  lapse_count += 1

next_review = today + interval_new days
review_count += 1
last_quality = q
last_review = today
```

按 `concept_id` 同步更新 `model.json` 和 `schedule.json`。如果 schedule 还是旧版数组结构，先迁移为 `{version, items}`；不要追加重复概念。

`st-recall` 不修改 mastery，即使用户表现很好也不提升；如果表现明显超过当前 mastery，在报告里建议用户运行 `/st-study {source-id}` 完成对应层级。

## 测试报告

全部题目结束后输出：

```text
━━ 召回测试报告 ━━
题目数: {N} | 通过: {X} | 部分通过: {Y} | 未通过: {Z}

薄弱概念:
- {概念名}: {具体薄弱点}

复习计划变化:
- {概念名}: next_review -> {日期}

建议下一步:
- {建议}
```

如果同一概念连续 3 次不通过，不要继续抽题折磨用户，建议回到 `/st-study {source-id}` 重学该概念。
