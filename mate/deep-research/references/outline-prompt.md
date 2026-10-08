# 研究大纲规范

## 目标

大纲不是文章目录，而是研究控制面。它必须让每个章节都能回到可验证的问题和证据需求。

## JSON 结构

```json
{
  "title": "研究标题",
  "language": "zh",
  "mode": "standard",
  "decision_to_support": "研究完成后要支持的决定",
  "scope": {
    "subject": "研究对象",
    "time_range": "2024-01-01 至 2026-07-30",
    "regions": ["中国", "美国"],
    "included": ["纳入内容"],
    "excluded": ["不纳入内容"]
  },
  "time_anchor": {
    "mode": "latest",
    "as_of": "2026-07-30",
    "reason": "用户需要当前状态"
  },
  "core_question": "一句可判定的主问题",
  "hypotheses": [
    {
      "statement": "暂定假设",
      "falsified_by": "什么证据会推翻它"
    }
  ],
  "chapters": [
    {
      "title": "章节标题",
      "purpose": "本章如何服务最终决定",
      "sections": ["分节一", "分节二"],
      "sub_questions": [
        {
          "id": "q1",
          "question": "可独立回答的问题",
          "priority": "high",
          "evidence_needed": ["原始统计", "反方案例"],
          "preferred_source_roles": ["primary", "secondary"],
          "counterevidence": "应主动寻找的反证",
          "coverage_exception": ""
        }
      ]
    }
  ]
}
```

## 约束

- `id` 在整个大纲中唯一且稳定。
- 每个高优先级问题直接影响主结论或建议。
- 问题应能由证据回答，避免“全面介绍”“深入分析”等空泛表达。
- `sections` 是写作结构，`sub_questions` 是取证结构；两者可以一对多。
- `time_anchor.mode`：
  - `latest`：强调当前状态，时间密度检查适用。
  - `user_specified`：按用户指定历史窗口，检查相应窗口。
  - `relaxed`：常青、历史或概念研究，不强制最新年份密度。
- 只有真实存在且可解释的例外才填写 `coverage_exception`。

## 生成前检查

1. 是否写清用户要做的决定。
2. 是否存在主题之外的隐性范围扩张。
3. 每个高优先级问题是否定义了首选原始来源。
4. 是否安排了反证或失败案例。
5. 章节数量是否落在所选模式范围内。
6. 是否能从全部子问题重新构造主问题的答案。

