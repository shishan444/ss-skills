---
name: st-digest
description: 处理新的学习材料，尤其是用户给出 PDF、文章或学习资料路径并希望“提取知识结构、生成题库、开始学习、做成学习系统”时必须使用。它负责把原始材料转成 learning/extractions、learning/questions 和 index，不负责带用户学习；学习交互交给 st-study。
argument-hint: "<pdf-or-text-path>"
disable-model-invocation: true
allowed-tools: Read, Write, Glob, Grep, Bash
---

# st-digest — 学习材料摄取

把一份新材料变成后续所有 `st-*` skill 可以消费的学习数据：核心命题、概念图谱、三层知识结构、召回题库和 source 索引。

## 边界

`st-digest` 只做材料摄取和结构化，不进行互动教学，不更新学习者掌握度，不写入复习计划。学习状态从 `/st-study` 开始产生。

## 输入

- `$ARGUMENTS` 或 `$0`：PDF、Markdown、TXT 或其他可提取文本的学习材料路径。
- 路径可以是相对项目根目录，也可以是绝对路径。

## 数据目录

如果目录不存在，先创建：

- `learning/extractions/`
- `learning/questions/`
- `learning/materials/`
- `learning/learner/`

如果 `learning/` 不存在，不要报错退出，按上面的最小结构初始化。

## 执行流程

### 1. 验证与文本提取

1. 确认输入文件存在。
2. 生成 `source-id`：`{文件名去扩展名}-{YYYYMMDD}`，全小写，空格和下划线转连字符，只保留字母、数字、中文和连字符。
3. 如果 `learning/extractions/{source-id}.md` 已存在，先告知用户，并询问覆盖、另存为新 source-id，还是取消。
4. 提取正文：
   - Markdown/TXT：直接读取。
   - PDF：按顺序尝试 `pdftotext`；如果不可用，再尝试当前 Python 环境已安装的 `pypdf` 或 `pdfplumber`；都不可用或提取为空时停止。
   - 如果 PDF 是扫描件或文本提取失败，明确告诉用户需要 OCR 或可复制文本版本，不要伪造内容，也不要只凭文件名推断内容。
5. 如果材料很长，先建立全局目录和章节摘要，再进入概念提取；不要只读开头。

### 2. 识别核心命题

先回答三个问题，再提取概念：

- 这份材料主要在解决什么矛盾或问题？
- 作者给出的核心机制、模型或判断是什么？
- 哪些内容是结论，哪些只是例子、背景或论证材料？

核心命题不是标题复述，也不是术语定义。它应该是拿掉以后整份材料会塌掉的那根承重梁。

### 3. 提取概念图谱

按本 skill 目录下 `references/extraction-guide.md` 的标准控制粒度。

每个概念必须满足：

- 可以独立解释。
- 可以独立测试。
- 可以迁移到别的语境。
- 不是纯术语表，也不是章节标题。

数量参考：

- 论文：3-6 个。
- 技术文档/API：3-8 个。
- 教科书章节：5-10 个。
- 学术著作或长材料：10-20 个。

同时构建关系：

- `prerequisites`：硬前置依赖，学 B 前必须先懂 A。
- `parallel`：同层并列。
- `deepens`：B 是 A 的深化。

依赖图必须无环。若出现环，先合并或重切概念粒度。

**概念 ID 规则**：

- 每个概念生成稳定 `concept_id`，格式为 `{source-id}--{concept-slug}`。
- `concept-slug` 来自概念名：全小写，空格和下划线转连字符，只保留字母、数字、中文和连字符。
- 同名冲突时追加 `-2`、`-3`。
- 后续即使概念显示名微调，也优先保留原 `concept_id`，避免笔记、题库和复习计划断链。

### 4. 为每个概念写三层内容

#### 简化层

必须包含：

- 一句话定义。
- 它为什么存在，解决什么矛盾。
- 核心机制的日常语言解释。
- 反直觉点；如果没有，就写“这个概念的直觉方向和表面理解基本一致”。

不要用另一个未解释术语解释当前术语。

#### 精度层

必须写清：

- “简化版遮掉了什么”。
- 哪些技术细节、数学结构、前提条件或边界被省略了。
- 在什么场景下，只用简化版会判断错。

精度层不是堆细节，而是说明哪些细节会改变判断。

#### 拓展层

必须包含：

- 至少 1 个结构同构，不接受只靠词汇相似的类比。
- 明确映射：A 的哪个要素对应 B 的哪个要素。
- 现实应用场景。
- 如果 `learning/learner/profile.md` 存在，可以尝试连接学习者已有锚点；找不到就写“未发现可靠个人锚点”，不要硬连。

### 5. 生成召回题库

为每个概念生成 3 类开放式题目：

- `L1_identify`：给一段场景或描述，让学习者识别概念，题干不要直接出现概念名。
- `L2_explain`：要求学习者用自己的话解释，并列出 2-3 个必须包含的要素。
- `L3_transfer`：给一个原文没有出现的新情境，让学习者判断同构机制如何起作用。

题目服务于评估，不服务于背诵。不要生成只有标准答案的选择题。

### 6. 写入文件

写入 `learning/extractions/{source-id}.md`：

```markdown
---
source_id: {source-id}
title: {材料标题}
material_path: {原始材料路径}
created: YYYY-MM-DD
concept_count: {N}
---

# {材料标题}

## 核心命题

## 学习顺序
- {概念A}
- {概念B}

## 概念图谱
### 硬依赖
- {概念B} <- {概念A}

### 并列/递进
- {概念A} || {概念C}
- {概念D} deepens {概念B}

## Concepts

### {概念名}
id: {source-id}--{concept-slug}
prerequisites: [...]

#### 简化层

#### 精度层

#### 拓展层
```

写入 `learning/questions/{source-id}.json`：

```json
{
  "source_id": "source-id",
  "created": "YYYY-MM-DD",
  "questions": [
    {
      "concept_id": "{source-id}--{concept-slug}",
      "concept": "概念名",
      "items": {
        "L1_identify": [{"question": "...", "expected": "..."}],
        "L2_explain": [{"question": "...", "must_include": ["...", "..."]}],
        "L3_transfer": [{"question": "...", "transfer_signal": "..."}]
      }
    }
  ]
}
```

更新 `learning/extractions/index.md`，追加：

```markdown
- `{source-id}` | {材料标题} | {N} concepts | {created}
```

### 7. 完成摘要

向用户输出：

- `source-id`
- 提取的概念数量。
- 核心命题一句话。
- 概念依赖图的文本表示。
- 建议学习顺序。
- 下一步命令：`/st-study {source-id}`；如果还没有画像，建议 `/st-profile`。

## 质量自检

提交前逐项检查：

- 核心命题不是标题复述。
- 概念数量合理，没有过粗或过碎。
- 每个概念都有简化层、精度层、拓展层。
- 每个精度层都说明“简化版遮掉了什么”。
- 每个拓展层都有可映射的结构同构，或明确说明没有可靠同构。
- 题库是开放式问题，并能区分识别、解释、迁移。
- `source-id` 在 extraction、questions、index 中一致。

## 参考文件

- `references/extraction-guide.md`：概念粒度、三层内容、同构和题目质量标准。
