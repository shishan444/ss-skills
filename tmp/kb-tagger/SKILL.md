---
name: kb-tagger
description: >
  知识库元数据与关联管理。三种模式：tag-gen（标签填充）、tag-normalize（标签规范化）、
  link（双向链接）。对已有笔记进行后处理，生成/更新 frontmatter 元数据，
  建立笔记间的双向关联。当用户要求给笔记打标签、整理标签体系、
  建立笔记关联时触发。
disable-model-invocation: true
---

# 知识库元数据与关联管理

kb-tagger 有三种独立模式，对已有笔记进行后处理。

## 模式识别

根据用户意图选择模式，然后 Read 对应的模式文件和 frontmatter-schema.md：

| 用户意图 | 模式 | 加载文件 |
|---------|------|---------|
| 给笔记添加/更新标签、填充 frontmatter | tag-gen | references/mode-tag-gen.md + references/frontmatter-schema.md |
| 整理标签体系、合并重复标签 | tag-normalize | references/mode-tag-normalize.md + references/frontmatter-schema.md |
| 建立笔记间关联、双向链接 | link | references/mode-link.md + references/frontmatter-schema.md |

## 字段维护者

| 字段 | 维护者 | tag-gen | tag-normalize | link |
|------|--------|---------|---------------|------|
| anchor | 人 | 不触碰 | 不触碰 | 不触碰 |
| tags | 机器 | 生成/更新 | 归一化 | 不触碰 |
| leads | 机器 | 生成/更新 | 归一化 | 不触碰 |
| aliases | 机器 | 生成/更新 | 不触碰 | 不触碰 |
| support/resonate/tension/instance | link 模式 | 不触碰 | 不触碰 | 增量补充 |

## 通用安全规则

- 写入只追加，不覆盖已有值
- 不修改 anchor 字段
- 保留分组注释结构（`# ▼ 人维护` / `# ▼ LLM 维护`）
- 所有写入前展示结果供用户审核确认
- tag-gen / tag-normalize 不修改正文内容
- link 模式仅在 `## 脉络` 段追加，不修改其他段落

## 反面代价

覆盖整个 frontmatter 或修改正文内容会导致：
- 已有 Obsidian 链接失效
- connections 字段及理由文本丢失
- 分组结构破坏
- 这些损失在知识库规模大时几乎无法手动修复
