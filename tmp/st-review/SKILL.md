---
name: st-review
description: 用户想“间隔复习、今天该复习什么、复习到期概念、按遗忘曲线复习、运行复习计划”时使用。它读取 learning/schedule.json，筛选到期概念，做开放式召回并按 SM-2 更新下一次复习时间；不负责学习新概念，也不提升 mastery。
disable-model-invocation: true
allowed-tools: Read, Write, Glob, Grep
---

# st-review — 间隔复习

基于 `learning/schedule.json` 做到期复习。它解决的是“什么时候该把已学概念重新取出来”的问题，而不是“怎么第一次学会”。

## 边界

`st-review` 只处理已经进入复习周期的概念，通常是 `mastery >= 2`。它可以更新复习参数和误解记录，但不提升 mastery。连续复习失败时，建议回到 `st-study` 重学。

## 前置检查

1. 读取 `learning/schedule.json`。
2. 读取 `learning/learner/model.json`。
3. 读取相关 `learning/extractions/*.md` 和 `learning/questions/*.json`。
4. 读取本 skill 的参考文件：`references/sm2-algorithm.md`。

如果 `schedule.json` 不存在或为空，告诉用户还没有概念进入复习周期，并建议先运行 `/st-study {source-id}`。

## schedule.json 最小结构

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

兼容旧格式：如果 schedule 是数组，按数组读取；写回时迁移为 `{version, items}`。后续所有 skill 都按 `concept_id` 合并 item，不按概念名合并。

## 筛选到期概念

到期条件：`next_review <= 今天`。

如果没有到期概念，输出：

```text
当前没有到期复习任务。
下一次复习: {最近日期}，{距今天数} 天后。
概念总数: {总数} | 待复习: 0
想提前复习可以用 /st-recall random。
```

如果有到期概念，按优先级排序：

1. `next_review` 逾期越久越优先。
2. `easiness` 越低越优先。
3. `lapse_count` 越高越优先。
4. `mastery` 越低越优先。

默认一次最多复习 7 个概念。超过 7 个时，先说明积压数量，并询问用户是否只做前 7 个、全部做完、或指定数量。

## 复习问题选择

按 `review_count` 和 `mastery` 决定难度：

- `review_count 0-1`：解释核心机制，优先 `L2_explain`。
- `review_count 2-3`：要求说明精度层、边界或容易误判的场景。
- `review_count >= 4`：要求迁移到新情境，优先 `L3_transfer`。

如果题库缺题，就根据 extraction 临时生成一题，并标注“临时题”。

## 逐个复习

对每个到期概念：

```text
━━ 复习 {N}/{总数}: {概念名} ━━
来源: {source-id} | 上次复习: {last_review} | 复习次数: {review_count}

{问题}
```

等待用户回答。不要替用户回答。

评估时看三点：

- 核心结构是否完整。
- 是否用自己的话取回，而不是只背关键词。
- 当前难度要求的边界或迁移是否出现。

反馈必须具体：

```text
{通过/部分通过/不通过}
- 抓住了: {用户回答里的有效部分}
- 缺口: {遗漏或偏差}
- 下一次注意: {一句话}
```

## SM-2 更新

使用 `references/sm2-algorithm.md` 中的规则。内联执行时也必须与参考文件保持一致：

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

同步更新 `schedule.json` 和 `model.json` 中同一概念的复习字段。不要提升 mastery。

## 连续失败处理

如果某概念 `lapse_count >= 3` 或连续 3 次复习不通过：

- 在报告中标记为“需要重学”。
- 建议 `/st-study {source-id}` 回到该概念。
- 不要继续把它安排成长间隔。

## 复习报告

```text
━━ 复习报告 ━━
到期: {到期数} | 完成: {测试数} | 通过: {X} | 部分: {Y} | 未通过: {Z}

记忆状况:
- 牢固: {数量}
- 正常: {数量}
- 薄弱: {数量}
- 需要重学: {列表}

下次复习: {最近 next_review}
```

## 与其他 skill 的关系

- `st-study`：概念首次达到 `mastery >= 2` 时进入 schedule。
- `st-recall`：用户主动抽题，也会更新复习参数。
- `st-review`：只处理到期任务，是调度驱动的复习。
