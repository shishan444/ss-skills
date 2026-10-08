# 证据账本规范

## 设计原则

证据账本是追加式 JSONL 文件，每行代表一个已实际核验的网页或本地文件。它把“浏览过什么”与“报告声称什么”连接起来。

- 一条记录对应一个规范化来源。
- 一个来源可以包含多个主张。
- 短摘录只用于核验，不替代自己的表述。
- 数字必须保留单位、周期、范围和口径。
- 事实、估算、预测与观点必须分开。
- 搜索摘要不得写成已验证主张。

## 来源记录

```json
{
  "source_url": "https://example.com/report",
  "local_path": "",
  "title": "Report title",
  "publisher": "Example Institute",
  "published_at": "2026-05-12",
  "retrieved_at": "2026-07-30T20:00:00+08:00",
  "access_status": "verified",
  "failure_reason": "",
  "source_role": "primary",
  "extraction_method": "web-chrome-dom",
  "research_questions": ["q1", "q3"],
  "claims": []
}
```

`source_url` 与 `local_path` 二选一。URL 只允许 `http` 或 `https`，保存时移除片段和常见跟踪参数。

### `access_status`

- `verified`：页面或文件已打开并完成核验。
- `partial`：只能读取部分内容；必须填写 `failure_reason`。
- `blocked`：登录、验证码、频率或权限限制；必须填写 `failure_reason`，且不得附带未经核验的主张。
- `not_relevant`：页面已核验但没有可用于当前问题的内容。

访问失败记录也进入账本，使 `manifest.json` 能展示被拦截来源和替代情况。

### `source_role`

- `primary`：原始数据、法规、披露、论文、标准、产品官方文档。
- `secondary`：独立分析、专业媒体、综述、数据库二次整理。
- `discovery`：仅帮助发现其他来源，不能单独支撑高置信度主张。
- `local`：用户提供的本地资料。

### `extraction_method`

- `curl`
- `web-chrome-dom`
- `web-chrome-gui`
- `local-file`

## 主张记录

```json
{
  "statement": "该指标在 2025 年为 42%",
  "kind": "fact",
  "metric": "采用率",
  "value": "42",
  "unit": "%",
  "period": "2025",
  "scope": "样本覆盖地区",
  "data_type": "actual",
  "confidence": "high",
  "support": "direct",
  "locator": "表 3，第 12 页",
  "quote": "Adoption reached 42 percent in 2025.",
  "contradicts": []
}
```

### 字段约束

- `statement`：报告可复述的原子主张；不得混合多个因果链。
- `kind`：`fact` 或 `opinion`。
- `data_type`：`actual`、`estimate`、`forecast` 或 `opinion`。
- `confidence`：`high`、`medium` 或 `low`，表示证据可靠性而非模型自信。
- `support`：`direct`、`indirect` 或 `context`。
- `locator`：页码、章节、表格、DOM 标题或本地行号，必须足以复核。
- `quote`：可选的短摘录；只保留核验主张所需的最小片段。
- `contradicts`：与该主张冲突的证据 ID 列表。

若主张含数字，`metric`、`value`、`unit`、`period` 和 `scope` 必须齐全。无法确认的字段不要猜测；应将问题标为证据缺口。

## 证据 ID 与去重

脚本根据规范化 URL 或本地路径、定位信息和主张文本生成稳定的 `evidence_id`。同一来源重复加入时合并研究问题和不重复主张。

不同网页转载同一原始材料不算独立证据。覆盖统计优先按 `publisher` 和规范化域名去重。

## 数据池映射

`evidence_ledger.py export-datapool` 将账本按子问题生成：

```json
{
  "question_id": "q1",
  "question": "核心问题",
  "priority": "high",
  "src": ["Example Institute"],
  "facts": [
    {
      "src": "Example Institute",
      "yr": "2025",
      "met": "采用率",
      "val": "42",
      "u": "%",
      "ctx": "样本覆盖地区",
      "url": "https://example.com/report",
      "title": "Report title",
      "conf": "high",
      "data_type": "actual",
      "source_role": "primary",
      "evidence_id": "ev_...",
      "locator": "表 3，第 12 页"
    }
  ],
  "gaps": [],
  "coverage_status": "supported"
}
```

没有事实但明确存在缺口的记录在结构上有效，`facts` 为空，`gaps` 不为空，`coverage_status` 为 `insufficient`。校验器不能逼迫写作者捏造一条“事实”来通过检查。

## 引用规则

- 报告正文的 `[N]` 映射到数据池的唯一来源条目。
- 引用放在它支持的句子或段落后。
- 同一引用不得被用来支持来源中不存在的新结论。
- 推断应写成“据此推断”并同时引用构成推断的证据。
- 本地资料引用需在参考来源中给出文件名和定位，不泄露不必要的绝对路径。
