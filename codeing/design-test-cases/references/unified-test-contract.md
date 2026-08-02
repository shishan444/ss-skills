# 统一测试产物契约

## 目录

1. 产物关系
2. `test-design.md` 契约
3. `test-cases.json` 顶层结构
4. 统一用例字段
5. 三层扩展字段
6. 覆盖与交叉引用
7. 自动调用与回归
8. 统一运行结果协议
9. 最小示例

## 1. 产物关系

一次完整设计默认产生：

- `test-design.md`：解释需求基线、方案、分层理由、业务流程、风险、覆盖和取舍。
- `test-cases.json`：记录机器可读取、可校验、可交给不同执行适配器的正式用例。

两者必须共享相同的来源 ID、验证命题 ID、流程 ID、覆盖义务 ID 和用例 ID。Markdown 不得包含 JSON 中没有的“隐形正式用例”；JSON 不得出现设计文档无法解释的孤立用例。

## 2. `test-design.md` 契约

至少包含：

1. 结论与 `ready`、`conditional` 或 `blocked` 状态。
2. 已确认事实、推导、假设、关键未知及来源。
3. 范围、非范围和受保护价值。
4. L1、L2、L3 的主责边界和不重复理由。
5. L2 业务流程模型和 L3 关键用户旅程。
6. 风险链和验证命题。
7. 覆盖义务矩阵：来源、类型、主责层、用例和状态。
8. 用例摘要：ID、层级、类别、目标、优先级和运行档位。
9. 自动化适配、数据环境、证据和回归门禁。
10. 未覆盖项、剩余风险、停止判断和设计审批状态。

## 3. `test-cases.json` 顶层结构

根对象必须包含：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `schema_version` | string | 当前固定为 `1.0` |
| `requirement` | object | 需求标题、版本、来源、事实和就绪状态 |
| `design_gate` | object | 设计审批状态及实施前审批约束 |
| `strategy` | object | 范围、价值、三层与三类覆盖处置、运行档位 |
| `flow_models` | array | L2 业务流程的节点、边、终态和副作用 |
| `propositions` | array | 从需求、规则或风险得到的验证命题 |
| `coverage_obligations` | array | 可审查的覆盖分母与处置状态 |
| `cases` | array | 统一格式测试用例 |
| `coverage_summary` | object | 已覆盖、条件、阻断、未覆盖和停止判断 |

### `requirement`

```json
{
  "title": "购物车重复添加",
  "version": "2026-07-31",
  "source_ids": ["REQ-CART-001"],
  "readiness": "ready",
  "known_facts": [
    {
      "fact_id": "F-001",
      "statement": "已登录用户顺序添加同一 SKU 两次后只保留一行且数量为 2",
      "source_ids": ["REQ-CART-001"]
    }
  ],
  "assumptions": [],
  "critical_unknowns": []
}
```

`readiness` 只允许 `ready`、`conditional`、`blocked`。

### `design_gate`

```json
{
  "status": "draft",
  "approval_required_before_implementation": true,
  "blocking_reasons": [],
  "approved_by": null
}
```

`status` 只允许 `draft`、`approved`、`blocked`。未经实际确认不得擅自使用 `approved`。

### `strategy`

```json
{
  "protected_values": ["重复操作不会产生重复商品行"],
  "scope_in": ["已登录用户顺序添加同一 SKU"],
  "scope_out": ["并发添加与游客购物车"],
  "layers": {
    "L1": {"disposition": "cases", "rationale": "聚合规则在领域层产生"},
    "L2": {"disposition": "cases", "rationale": "需验证接口、事务与数据库"},
    "L3": {"disposition": "cases", "rationale": "需验证按钮和页面状态"}
  },
  "categories": {
    "positive": {"disposition": "cases", "rationale": "验证目标状态"},
    "negative": {"disposition": "cases", "rationale": "验证非法前置被拒绝"},
    "risk": {"disposition": "not_applicable", "rationale": "当前材料未建立额外风险机制；并发作为待确认范围"}
  },
  "run_profiles": ["local", "pr", "scheduled", "release", "post_deploy", "exploration"]
}
```

每个层级和类别的 `disposition` 只允许 `cases` 或 `not_applicable`。使用 `not_applicable` 必须给出具体理由。

### `flow_models`

```json
{
  "flow_id": "FLOW-CART-ADD",
  "name": "顺序重复添加商品",
  "entry": "POST /cart/items 或页面加入购物车按钮",
  "nodes": [
    {"node_id": "N-CART-EMPTY", "state": "空购物车"},
    {"node_id": "N-CART-QTY1", "state": "SKU 数量 1"},
    {"node_id": "N-CART-QTY2", "state": "SKU 数量 2"}
  ],
  "edges": [
    {"edge_id": "E-CART-ADD1", "from": "N-CART-EMPTY", "action": "添加 SKU-A", "guard": "SKU 可添加", "to": "N-CART-QTY1"},
    {"edge_id": "E-CART-ADD2", "from": "N-CART-QTY1", "action": "再次添加 SKU-A", "guard": "SKU 可添加", "to": "N-CART-QTY2"}
  ],
  "terminal_states": [
    {"terminal_id": "T-CART-SUCCESS", "state": "单商品行且数量为 2", "type": "success"}
  ],
  "critical_side_effects": [
    {"side_effect_id": "SE-CART-NO-DUP", "description": "不得创建第二个相同 SKU 商品行"}
  ]
}
```

终态 `type` 只允许 `success`、`rejected`、`failed`、`recovered`。
节点、边、终态和副作用 ID 在整个清单内必须唯一；它们共同构成业务链路覆盖分母。

### `propositions`

```json
{
  "proposition_id": "VP-001",
  "source_ids": ["REQ-CART-001"],
  "context": "已登录用户拥有空购物车且 SKU 可添加",
  "stimulus": "顺序添加同一 SKU 两次",
  "expected": "购物车只有一个该 SKU 商品行且数量为 2",
  "invariants": ["同一购物车同一 SKU 最多一个商品行"],
  "risk_if_broken": "重复商品行导致数量和计价错误"
}
```

## 4. 统一用例字段

每个 `cases[]` 对象必须包含：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `case_id` | string | 稳定且唯一，推荐 `TC-L1-001` |
| `title` | string | 描述一个主要验证目标 |
| `source_ids` | string[] | 至少一个真实来源 |
| `proposition_ids` | string[] | 至少一个且必须存在 |
| `obligation_ids` | string[] | 至少一个且必须存在 |
| `layer` | string | `L1`、`L2`、`L3` |
| `responsibility` | string | `primary` 或 `reinforcement` |
| `category` | string | `positive`、`negative`、`risk` |
| `priority` | string | `critical`、`high`、`normal` |
| `owner` | string | 对语义、实现、稳定性和退役负责的团队或角色 |
| `lifecycle_status` | string | `draft`、`reviewed`、`automated`、`regression_active`、`quarantined`、`retired` |
| `intent` | string | 保护的价值或消除的不确定性 |
| `preconditions` | string[] | 角色、数据、状态、环境和依赖 |
| `stimulus` | string[] | 明确输入、动作或事件 |
| `oracle` | object | 必须、禁止及时间边界 |
| `controls` | object | 数据、依赖、时间和随机性控制 |
| `cleanup` | string | 清理、回滚或一次性环境策略 |
| `evidence` | string[] | 响应、状态、日志、截图等证据 |
| `automation` | object | 执行适配器和回归元数据 |
| `layer_detail` | object | 对应层级的必需扩展字段 |

### `oracle`

```json
{
  "must": ["购物车中 SKU-A 恰好一行", "数量为 2"],
  "must_not": ["出现第二个 SKU-A 商品行"],
  "time_boundary": "第二次请求完成后立即成立"
}
```

`must` 至少一项；没有禁止结果时 `must_not` 使用空数组。时间不相关时明确写“不适用：同步确定性结果”，不要含糊省略。

### `controls`

```json
{
  "data": "为用例创建独立用户、购物车和 SKU",
  "dependencies": "使用真实测试数据库；外部库存依赖使用契约模拟",
  "time_randomness": "固定时钟和随机 ID 生成器"
}
```

### `automation`

```json
{
  "adapter": "pytest",
  "entrypoint": "tests/cart/test_add_same_sku.py::test_add_twice",
  "run_profiles": ["local", "pr", "scheduled"],
  "deterministic": true
}
```

允许的 `run_profiles`：`local`、`pr`、`scheduled`、`release`、`post_deploy`、`exploration`。尚未实现时，`entrypoint` 写入计划路径并在设计文档中标记“待实施”，不要伪造已经执行。

## 5. 三层扩展字段

### L1

```json
{
  "unit_under_test": "Cart.add_item",
  "rule_or_invariant": "相同 SKU 合并商品行并增加数量",
  "test_doubles": ["固定 SKU 可购买策略，隔离非本命题外部依赖"]
}
```

### L2

```json
{
  "flow_ids": ["FLOW-CART-ADD"],
  "business_entry": "POST /cart/items",
  "end_state": "数据库和 API 均表示单行且数量为 2",
  "side_effects": ["不得新增第二个相同 SKU 商品行"],
  "covered_flow_elements": {
    "node_ids": ["N-CART-EMPTY", "N-CART-QTY1", "N-CART-QTY2"],
    "edge_ids": ["E-CART-ADD1", "E-CART-ADD2"],
    "terminal_ids": ["T-CART-SUCCESS"],
    "side_effect_ids": ["SE-CART-NO-DUP"]
  }
}
```

每个 L2 用例至少引用一个存在的 `flow_id`，并声明本用例实际承接的流程元素。一个清单内所有已建模流程元素必须至少被一个 L2 用例承接；否则“业务链路系统性覆盖”校验失败。

### L3

```json
{
  "role": "已登录消费者",
  "start_state": "已登录、空购物车、商品详情页",
  "core_action_via_ui": true,
  "tool": "Chrome MCP",
  "mode": "regression",
  "locator_strategy": "按可访问名称定位‘加入购物车’按钮",
  "observations": ["页面购物车行和数量", "购物车 API", "控制台错误", "关键步骤截图"]
}
```

`core_action_via_ui` 必须为 `true`；`mode` 只允许 `regression` 或 `exploration`。

## 6. 覆盖与交叉引用

### `coverage_obligations`

```json
{
  "obligation_id": "OB-001",
  "source_ids": ["REQ-CART-001"],
  "proposition_ids": ["VP-001"],
  "type": "rule",
  "description": "同一购物车同一 SKU 保持单商品行",
  "protected_value": "重复操作不会破坏购物车数据",
  "failure_mechanism": "第二次添加直接创建新行",
  "criticality": "high",
  "primary_layer": "L1",
  "case_ids": ["TC-L1-001", "TC-L2-001", "TC-L3-001"],
  "status": "designed",
  "residual_risk": "尚未验证并发添加"
}
```

`type` 允许：`requirement`、`rule`、`state`、`flow`、`permission`、`dependency`、`interaction`、`risk`。

`status` 允许：`designed`、`conditional`、`blocked`、`accepted`、`not_applicable`。关键或高风险义务不得由 LLM 自行标记为 `accepted`；必须记录真实责任人决定。

### `coverage_summary`

```json
{
  "covered_obligation_ids": ["OB-001"],
  "conditional_obligation_ids": [],
  "blocked_obligation_ids": [],
  "uncovered_items": [
    {"description": "并发添加", "reason": "需求与入口机制待确认", "owner": "产品负责人"}
  ],
  "stop_decision": "conditional_complete",
  "rationale": "顺序添加需求已闭合，并发风险保持可见"
}
```

`stop_decision` 允许：`continue`、`conditional_complete`、`complete`、`blocked`。

## 7. 自动调用与回归

统一调度器应按以下字段选择用例：

- `layer`：选择 L1、L2、L3。
- `category`：选择正向、反向、风险。
- `priority`：形成硬门禁或常规回归。
- `automation.run_profiles`：按本地、PR、定时、发布、部署后、探索运行。
- `automation.adapter` 与 `entrypoint`：交给实际执行器。
- `controls` 与 `cleanup`：准备和恢复可重复环境。
- `evidence`：聚合执行证据。

测试代码可以因框架或架构重构而改变，但稳定 ID、来源、验证命题和覆盖义务不得无理由丢失。
测试用例必须和业务代码一样拥有责任人、评审状态和正式退役路径；维护困难不能成为无记录删除覆盖义务的理由。

## 8. 统一运行结果协议

执行适配器至少返回：

```json
{
  "case_id": "TC-L1-001",
  "version": "git-sha-or-build-id",
  "environment": "ci-pr",
  "adapter": "pytest",
  "started_at": "2026-07-31T10:00:00Z",
  "duration_ms": 42,
  "result": "PASS",
  "expected_actual_diff": null,
  "evidence_locations": ["artifacts/TC-L1-001.log"],
  "preliminary_classification": null
}
```

`result` 只允许：

- `PASS`：声明条件下验证命题成立。
- `FAIL`：产品行为违反测试契约。
- `ERROR`：环境、基础设施或执行器无法完成验证。
- `SKIPPED`：未执行，不能计为通过。
- `QUARANTINED`：已知不稳定，不提供硬门禁证据。

## 9. 最小示例

完整清单可以包含多个流程、命题、义务和用例，但不得删除顶层字段。最小有效清单仍需：

- 三层和三类全部得到 `cases` 或 `not_applicable` 处置。
- 至少一个验证命题、覆盖义务和测试用例。
- 每条用例具有明确 oracle、控制、清理、证据和自动化元数据。
- 所有 ID 引用存在且唯一。
- L2 用例引用流程模型；L3 用例声明真实界面工具与 `core_action_via_ui: true`。
- 设计门明确要求实施前审批。

使用 `scripts/validate_test_manifest.py` 检查结构和交叉引用。结构校验通过不等于测试语义正确，仍需产品、研发和测试共同评审。
