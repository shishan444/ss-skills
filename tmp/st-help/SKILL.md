---
name: st-help
description: 用户第一次使用学习助手、问 st-* 怎么用、忘记流程、想知道学习系统能做什么、或需要选择 st-digest/st-study/st-review/st-notes/st-connect/st-profile/st-recall 中哪个 skill 时使用。它只解释流程和建议下一步，不直接处理材料。
disable-model-invocation: true
allowed-tools: Read, Glob
---

# st-help — 学习助手使用指南

`st-*` 是一套个人学习闭环：把材料变成概念结构，让用户主动召回，再把用户自己的理解沉淀为笔记和跨域连接。

## 一句话理解

这套系统不是“总结 PDF”。它的核心是让用户说出自己的理解，并把这些表述持续写入学习状态、复习计划和知识笔记。

## 快速路径

第一次使用，推荐：

```text
/st-digest <材料路径>     # 摄取 PDF/文章，生成概念、三层内容和题库
/st-profile              # 建立学习者画像，提取个人认知锚点
/st-study <source-id>    # 开始三层递进学习
/st-notes <source-id>    # 把学习者表述沉淀成笔记
/st-review               # 按间隔计划复习
```

如果用户只是想快速开始，也可以先 `/st-digest` 再 `/st-study`，之后补 `/st-profile`。

## 系统地图

```text
原始材料
  |
  v
/st-digest  ->  learning/extractions + learning/questions
  |
  v
/st-study   ->  learner/model + sessions + schedule
  |
  +--> /st-notes    -> learning/notes
  +--> /st-review   -> 到期复习
  +--> /st-recall   -> 主动自测
  +--> /st-connect  -> 认知桥梁

/st-profile -> learner/profile，为 digest/study/connect 提供个人锚点
```

## 各 skill 分工

### /st-digest

把 PDF、文章或学习材料变成结构化学习数据。

输出：

- `learning/extractions/{source-id}.md`
- `learning/questions/{source-id}.json`
- `learning/extractions/index.md`

它不带用户学习，只准备材料。

### /st-profile

通过领域扫描、教学探测、反向追问，建立学习者画像。

输出：

- `learning/learner/profile.md`

它的作用是找个人锚点，让新概念能挂到用户熟悉的结构上。

### /st-study

核心学习会话。逐个概念走三层：

1. 简化层：能不能讲出核心机制。
2. 精度层：知不知道简化版遮掉了什么。
3. 拓展层：能不能迁移到新领域或识别同构。

它是唯一默认推进 `mastery` 的 skill。

### /st-recall

主动自测。用户想“随机问我几个”“测测某个概念”时用。

它更新复习参数，但不提升 `mastery`。

### /st-review

间隔复习。读取 `learning/schedule.json`，筛选到期概念，按 SM-2 更新下次复习时间。

它是“到点了该复习什么”的调度器。

### /st-notes

从会话日志和 model 中提取用户原话，生成 Obsidian 兼容 Markdown 笔记。

默认输出：

- `learning/notes/{concept}.md`

笔记可以后续迁移到本 vault 的 `02知识库/`。

### /st-connect

扫描已学概念，寻找跨来源、跨领域的结构同构。

它只在用户确认后写入 `profile.md` 的认知桥梁，避免泛泛类比污染知识网络。

## 数据目录

```text
learning/
  materials/       # 原始材料，可选
  extractions/     # digest 后的概念结构
  questions/       # 召回题库
  learner/
    profile.md     # 学习者画像
    model.json     # 概念掌握度和复习参数
    sessions/      # 学习会话日志
  notes/           # 个人学习笔记
  schedule.json    # 间隔复习计划
```

如果 `learning/` 不存在，相关 skill 会按需初始化。

## 常见场景

**我刚拿到一份 PDF**

```text
/st-digest learning/materials/file.pdf
/st-study {source-id}
```

**我想继续上次学习**

```text
/st-study {source-id}
```

`st-study` 会根据 `model.json` 找到第一个未完成概念。

**我想知道今天该复习什么**

```text
/st-review
```

**我想随便抽几个问题测自己**

```text
/st-recall random
```

**我想把学过的东西变成笔记**

```text
/st-notes {source-id}
```

**我觉得知识之间有联系，想让系统帮我找**

```text
/st-connect
```

## 关键规则

- `mastery` 由 `st-study` 推进；`st-recall` 和 `st-review` 不直接提升。
- 没有用户主动回答，就不要假装完成学习。
- 个人笔记优先保留用户原话，标准内容只能做补充。
- 跨域连接必须有结构映射，并且最好经过用户确认。
- 找不到材料、题库或学习状态时，先告诉用户缺什么，再给下一步命令。

## 诊断下一步

当用户不知道该用哪个 skill：

- 有新材料：用 `/st-digest`。
- 已有 source-id，想学：用 `/st-study`。
- 想自测：用 `/st-recall`。
- 想复习到期内容：用 `/st-review`。
- 想产出笔记：用 `/st-notes`。
- 想找跨域连接：用 `/st-connect`。
- 想让系统更懂自己的知识背景：用 `/st-profile`。
