# kb-note Frontmatter 结构

## 完整字段

```yaml
---
# ▼ 人维护（必填）
anchor: "核心判断"

# ▼ 机器维护 —— kb-tagger tag-gen / tag-normalize 操作
tags: [标签1, 标签2]
leads: [线索词1, 线索词2]
aliases: [别名1, English Name]

# ▼ link 模式维护
support:
  - "[[笔记A]] 理由"
resonate:
  - "[[笔记B]] 理由"
tension:
  - "[[笔记C]] 理由"
instance:
  - "[[笔记D]] 理由"
---
```

## 字段语义

| 字段 | 类型 | 内容 | 判断测试 |
|------|------|------|---------|
| anchor | string | 一句话核心判断 | 删掉其他所有内容，理解还能被激活吗？ |
| tags | string list | 这条笔记**讲的是什么**——领域、主题、分类 | 你会用这个词**分类归档**这条笔记吗？ |
| leads | string list | **什么词会带你到这条笔记**——人物、类比、场景 | 你会在搜索框里**敲这个词**来找这条笔记吗？ |
| aliases | string list | 笔记标题的**其他叫法** | 换一种语言或说法，**同指一个概念**吗？ |
| support | list | A 为 B 提供基础 | A 被推翻，B 会动摇吗？ |
| resonate | list | A 和 B 共享深层结构 | 洞察能跨域迁移吗？ |
| tension | list | A 和 B 存在矛盾 | 两者能同时为真吗？ |
| instance | list | B 是 A 的具体案例 | 能说"B 是 A 的例子"吗？ |

## tags vs leads vs aliases 区分

三字段不应有重叠。如果一个词同时满足 tags 和 leads 的标准，优先放入 leads。

| 字段 | 属于的情况 | 示例 |
|------|-----------|------|
| tags | 领域分类 | `认知偏差` `行为经济学` `React` |
| leads | 检索线索 | `卡尼曼` `股票止损` `Dan Abramov` |
| aliases | 同义不同名 | `Loss Aversion` `损失规避` |

"巴菲特"属于 leads 不属于 tags——你不会用"巴菲特"来**分类归档**一条笔记，但你会搜"巴菲特"来**找到**它。

## connections 字段格式

```yaml
support:
  - "[[笔记名]] 一句话理由"
```

- 用双引号包裹，格式 `"[[]] 理由"`
- 理由是一句话，说明为什么存在这个关系
- 四种关系互斥，一条链接只属于一种类型

## 空值处理

字段为空时删除该字段，不保留 `[]`。Obsidian 将 `[]` 转为 null 导致显示异常。
