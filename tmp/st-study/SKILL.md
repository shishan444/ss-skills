---
name: st-study
description: 进入交互式学习会话时必须使用，尤其是用户说“开始学习、学这个 source、继续上次、带我学、逐个概念讲、用三层递进学习”或给出 source-id/topic 想学习。它负责呈现概念、要求学习者主动召回、更新 mastery 和会话日志；不负责首次摄取材料。
argument-hint: "<source-id-or-topic>"
disable-model-invocation: true
allowed-tools: Read, Write, Glob, Grep
---

# st-study — 三层递进学习会话

这是 `st-*` 系统的核心交互 skill。它把 `st-digest` 生成的概念结构变成一场可中断、可续传、可记录的学习会话。

## 边界

`st-study` 负责学习和掌握度推进。它可以更新：

- `learning/learner/model.json`
- `learning/schedule.json`
- `learning/learner/profile.md`
- `learning/learner/sessions/*.md`

它不重新提取材料，不批量生成笔记，不做间隔复习批处理。对应任务交给 `st-digest`、`st-notes`、`st-review`。

## 输入

- `$ARGUMENTS` 或 `$0`：`source-id`、概念名，或主题关键词。
- 如果用户没给参数，读取 `learning/extractions/index.md` 并列出可学习来源，让用户选择。

## 掌握度契约

`mastery` 只由 `st-study` 推进：

- `0`：未见过。
- `1`：看过简化层，但还没有通过召回。
- `2`：能用自己的话解释核心机制。
- `3`：理解精度层，知道简化版的边界和代价。
- `4`：能迁移到新情境或识别结构同构。

`st-recall` 和 `st-review` 可以影响复习间隔、易度和误解记录，但不直接提升 mastery。

## 前置检查

1. 读取或创建 `learning/learner/model.json`。
2. 读取 `learning/learner/profile.md`；不存在时提醒用户之后可运行 `/st-profile`，但不要阻断学习。
3. 根据参数定位 `learning/extractions/{source-id}.md`。
4. 如果参数是主题关键词，在 `learning/extractions/index.md` 和 extraction 正文中搜索匹配项。
5. 读取本 skill 的参考文件：
   - `references/assessment-criteria.md`
   - `references/interaction-patterns.md`

如果找不到任何 extraction，说明还没有可学习材料，建议先运行 `/st-digest <材料路径>`。

## model.json 最小结构

如果文件不存在，创建：

```json
{
  "version": 1,
  "concepts": {},
  "updated": "YYYY-MM-DD"
}
```

每个概念记录使用：

```json
{
  "concept_id": "{source-id}--{concept-slug}",
  "concept": "概念名",
  "source_id": "source-id",
  "mastery": 0,
  "attempts": 0,
  "correct_count": 0,
  "last_review": null,
  "easiness": 2.5,
  "interval_days": 1,
  "review_count": 0,
  "next_review": null,
  "last_quality": null,
  "lapse_count": 0,
  "misconceptions": [],
  "learner_outputs": [],
  "learner_notes_path": null
}
```

更新时按 `concept_id` 合并，不要用概念名当唯一键。不要删除未知字段；写入前先读取现有 JSON，改当前概念需要改的字段，再整体写回。

## 确定学习起点

1. 读取该 source 的学习顺序。
2. 找到第一个 `mastery < 4` 的概念。
3. 如果用户指定概念，就跳到该概念。
4. 显示进度概览：

```text
来源: {标题}
概念总数: {N} | 已完成: {mastery=4} | 进行中: {mastery 1-3} | 未开始: {mastery=0}
本次从「{当前概念}」开始。
```

一次只推进一个概念。用户明确要求继续时，再进入下一个概念。

## 三层递进循环

严格遵守“呈现后必须召回”。不要因为用户说“我懂了”就跳过召回。

### 第一层：简化层，目标 mastery 2

1. 呈现该概念的简化层。
2. 问用户是否需要补充解释；如果需要，可以补例子，但不要提前展开精度层。
3. 发出召回任务：

```text
用你自己的话解释「{概念名}」。请包含：
1. {核心机制}
2. {它解决的矛盾}
3. {反直觉点或关键边界}
```

4. 等待用户回答。不要替用户作答。
5. 按 `references/assessment-criteria.md` 评估：
   - 通过：`mastery = max(old, 2)`。
   - 部分通过：指出抓住了什么和漏了什么，允许最多 2 次重试。
   - 不通过：换一种解释方式，再重新召回。

### 第二层：精度层，目标 mastery 3

1. 呈现精度层，重点说明“简化版遮掉了什么”。
2. 发出召回任务：

```text
现在你看到了精度层。回答两个问题：
1. 简化版具体省略了什么？
2. 在什么场景下，只用简化版会判断错？
```

3. 通过后更新 `mastery = max(old, 3)`。
4. 如果用户只会复述精度细节，但说不出它改变了什么判断，视为部分通过。

### 第三层：拓展层，目标 mastery 4

1. 呈现拓展层中的结构同构和应用场景。
2. 如果 profile 中有相关锚点，说明映射；如果没有，不要硬连。
3. 发出召回任务：

```text
你在别的领域见过同样的骨架吗？说出一个，并指出哪里同构。
```

4. 用户找出的同构只要结构有效，就优先记录用户版本，而不是要求贴合 extraction 的例子。
5. 通过后更新 `mastery = max(old, 4)`，并请用户用一句话总结这个概念。
6. 将总结句和有效同构写入 `learner_outputs`，供 `st-notes` 使用。

## 更新规则

每次用户完成一次召回后，更新 `learning/learner/model.json`：

- `attempts += 1`
- 通过时 `correct_count += 1`
- `last_review = YYYY-MM-DD`
- 有持续误解时追加到 `misconceptions`
- 保存用户原话到 `learner_outputs`

当概念首次达到 `mastery >= 2`，写入或更新 `learning/schedule.json`。统一使用下面结构；如果遇到旧版数组结构，先读入再迁移为 `{version, items}`：

```json
{
  "version": 1,
  "items": [
    {
      "concept_id": "{source-id}--{concept-slug}",
      "concept": "概念名",
      "source_id": "source-id",
      "mastery": 2,
      "easiness": 2.5,
      "interval_days": 1,
      "review_count": 0,
      "last_review": "YYYY-MM-DD",
      "next_review": "YYYY-MM-DD",
      "last_quality": null,
      "lapse_count": 0
    }
  ]
}
```

同一个 `concept_id` 已存在时只更新该 item，不追加重复项。

如果学习者展现新的深度锚点或确认了跨域桥梁，可以追加到 `learning/learner/profile.md`，并标注来源为 `st-study`。

## 会话日志

会话结束、用户中断、或完成一个概念后，写入 `learning/learner/sessions/{YYYYMMDD}-{source-id}.md`。追加而不是覆盖。

```markdown
# 学习会话: {source-id} | {日期}

## 进度
- 起始概念: {概念}
- 结束概念: {概念}
- 本次推进: {数量} 个 mastery 阶段

## 概念记录

### {概念名}
- mastery: {旧值} -> {新值}
- 学习者表述: "{原话}"
- 评估: {通过/部分通过/不通过}
- 误解记录: {如有}
- 跨域映射: {如有}
```

## 用户控制命令

- “再解释一下”：补充解释，然后仍回到召回。
- “举个例子”：给例子，然后仍回到召回。
- “跳过”：标记 `mastery = max(old, 1)`，记录跳过原因，进入下一个概念。
- “回到 {概念名}”：切换到指定概念。
- “先看概览”：展示所有概念的一句话简介和依赖关系。
- “结束/暂停”：保存当前进度和会话日志。

## 输出节奏

每轮只给用户当前所需的信息。不要一次性把三层内容全倒出来。学习的关键不是展示内容，而是逼出学习者自己的表述。

完成一个概念后输出：

```text
概念完成: {概念名}
mastery: {旧值} -> {新值}
下一步: 继续下一个概念 / 生成笔记 / 暂停
```
