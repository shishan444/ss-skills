# 研究包与 Agent 交接合同

## 目录

1. 研究包结构
2. 主张与证据规则
3. 子任务合同
4. 研究增量
5. 分析增量
6. Master 的合并与完成判断

## 1. 研究包结构

研究包是 Master、研究 Agent 和分析 Agent 之间唯一的共同状态。Master 以 `assets/research-packet.template.json` 初始化；子 Agent 把结果写入父任务指定的增量文件，不直接写该研究包。

核心字段：

- `subject`：研究对象、用户问题、输入 URL 与截至时间；
- `workflow`：研究、分析、补查次数、交付恢复次数和当前阶段；
- `article`：输入文章的标题、发布者、发布时间和访问状态；
- `claims`：最小可核对主张；
- `evidence`：实际打开正文的来源；
- `timeline`：`before`、`trigger`、`current` 三类决定性节点；
- `viewpoints`：主体的结论、因果步骤、条件、证据与反证；
- `analysis`：事件性质、因果链和影响传播；
- `gaps`：不同答案会改变结论的缺口；
- `search`：来源预算、反方搜索和收敛原因；
- `completion`：最终完成状态与理由。

认识状态统一使用：

- `confirmed`：正文或可核查记录直接支持；
- `source_claim`：只能确认某主体这样说；
- `inference`：有事实锚点和连续机制，但结果未被直接证实；
- `disputed`：可靠材料存在实质冲突；
- `unknown`：当前不能赋值。

## 2. 主张与证据规则

每条重要表述先成为 `claim`，再进入时间线、观点或分析。`material=true` 表示改变事件定义、因果、影响方向或用户判断；它必须至少引用一条有效证据。

证据必须来自打开后的正文，而非搜索摘要。记录标题、发布者、日期、URL、正文定位和来源角色：

- `original`：原始文件、原始讲话、原始数据或当事方原始发布；
- `official`：依法或依职责发布信息的机构；
- `independent`：不依赖同一稿源的专业或新闻来源；
- `stakeholder`：利益相关方表态，只能证明其立场或行动；
- `background`：解释制度、行业或历史背景。

`claim.evidence_ids` 与 `evidence.claim_ids` 必须双向一致。转载同一稿源只计一个独立事实来源。`use_status=blocked` 的页面只记录访问受阻，不计有效来源。

## 3. 子任务合同

Master 每次派发以下对象，避免把整套开放问题交给 Agent：

```json
{
  "task_id": "T-RESEARCH-01",
  "objective": "本轮要确认或区分什么",
  "related_claim_ids": [],
  "inputs": {
    "article_url": "https://example.com/news",
    "packet_path": "works/tmp/.../research-packet.json",
    "task_dir": "works/tmp/...",
    "delta_path": "works/tmp/.../research-delta.json"
  },
  "done_gate": ["可重复判定的完成条件"],
  "budget": {
    "max_valid_sources": 12,
    "followup_rounds_remaining": 1,
    "delivery_recoveries_remaining": 1
  }
}
```

任务目标必须能在一个 Agent 回合内完成。只把“会改变判断的缺口”交给补查，不以“再多找一些信息”作为目标。

## 4. 研究增量

研究 Agent 把一个 JSON 对象写入父任务指定的 `research_delta_path`：

```json
{
  "task_id": "T-RESEARCH-01",
  "status": "complete | incomplete",
  "article_update": {},
  "claims_upsert": [],
  "evidence_upsert": [],
  "timeline_upsert": [],
  "gaps_upsert": [],
  "search_update": {
    "counter_search_done": true,
    "no_material_change_batches": 2,
    "stop_reason": "converged | budget_exhausted | access_blocked | insufficient"
  },
  "stop_reason": "为什么在这里停止"
}
```

若不能通过研究门禁，写入 `incomplete` 和具体缺口。文件落盘后只在消息中回报状态、路径和停止原因。不得返回观点因果、产业预测或最终报告。

## 5. 分析增量

分析 Agent 把一个 JSON 对象写入父任务指定的 `analysis_delta_path`：

```json
{
  "task_id": "T-ANALYZE-01",
  "status": "complete | needs_evidence | incomplete",
  "viewpoints_upsert": [],
  "analysis_update": {
    "nature": {},
    "causal_chains": [],
    "impacts": []
  },
  "material_gaps": [
    {
      "question": "缺什么证据",
      "changes": "该答案会改变哪项结论",
      "suggested_query": "最窄补查方向"
    }
  ],
  "stop_reason": "为什么分析已闭合或必须止步"
}
```

分析中的事实只能引用研究包已有 `claim_id` 或 `evidence_id`。分析 Agent 不添加新事实来源。文件落盘后只在消息中回报状态、路径和停止原因。

## 6. Master 的合并与完成判断

合并时按稳定 ID upsert，不按自然语言相似度合并。发现同一 ID 含义变化时，新建 ID；发现同一 URL 重复时保留信息更完整的一条。

Master 可以修复 JSON 形式和反向引用，但不能把 Agent 的候选提升为事实。任何会改变事实含义的修订都必须回到相应 Agent 或保留为缺口。

`workflow.followup_rounds` 记录内容层补查，`workflow.delivery_recoveries` 记录 Agent 已失联或未落盘后的同任务重派；两者均只能是 0 或 1。交付恢复必须沿用相同任务合同、输出路径和剩余预算，不得重置研究、扩大搜索或产生新事实。第二次交付失败直接进入 `incomplete`。

研究完成由 `validate_packet.py --phase research` 判定，最终完成由 `--phase final` 判定。脚本失败时先看失败属于：

1. 表示错误：不改变语义地修复；
2. 研究缺口：使用唯一一次补查或输出 `incomplete`；
3. 分析缺口：保留竞争分支或使用唯一一次补查；
4. 范围不适用：明确写 `not_applicable` 及理由，而不是删除字段。

来源预算达到上限、回答篇幅足够长、Agent 自称完成，均不是通过条件。
