# 页面池管理：15 硬上限 + 11 智能淘汰

> 加载时机：开 tab / 淘汰 tab 时（SKILL.md 端到端流程的"页面池"阶段）

## 两层阈值

```
0 ────────── 11 ─────────── 15
   正常区间    整理线  余量   硬上限
              ↑                ↑
              主动淘汰触发      cdp-proxy.mjs 兜底拒绝
```

- **11 = 主动整理触发点**：管理的 tab 达此数时，开新 tab 前**必须先淘汰一个**。`tab_manager.py acquire` 会拒绝并提示。
- **15 = 硬安全上限**：绝不突破。`cdp-proxy.mjs` 的 `checkTabPool()` 在此层兜底返回 429。

> **为何留 4 个余量？** 整理线与硬上限之间留 4 个 slot，避免边缘状态下（如并发子 agent 同时开 tab）无 tab 可用。`--force` 可绕过整理线但仍受硬上限兜底。

## 管理边界

本 skill **只管理自己创建的 tab**，绝不操作用户已有的 tab：
- 用户 Chrome 启动前已打开的 tab —— 不纳入管理，不计数，不淘汰
- 本 skill 通过 `/new` 或 `tab_manager.py acquire` 创建的 tab —— 纳入管理，状态记在 `~/.web-chrome-tabs.json`

操作前必须 `/targets` 快照（第一档规则1），区分哪些是本 skill 的 tab。

## 智能淘汰流程（LLM 判断价值，脚本管理机制）

```
tab_manager.py list
   │ 输出所有 tab 元数据 JSON（url/title/domain/task/pinned/openedAt/lastUsed）
   ▼
[LLM 按 5 维度评分]
   │ 每维度 1-5 分，总分最低者淘汰（pinned 免淘汰）
   ▼
tab_manager.py evict <target_id>
   │ 关闭选中 tab
   ▼
tab_manager.py acquire <new_url> --task <标签>
```

**脚本不替 LLM 做价值判断**——它只提供决策所需的元数据（list）和执行淘汰的机械能力（evict）。

## 5 维度评分表

每个 tab 按 5 个维度打分（1-5 分），**总分最低者先淘汰**：

| 维度 | 含义 | 5 分（保留） | 1 分（淘汰） |
|------|------|-------------|-------------|
| **信息完整度** | 目标内容是否已提取完毕 | 已提取完，无需再访问 | 尚未开始提取 |
| **任务相关性** | 与当前任务目标的关联度 | 核心来源，直接相关 | 跑题，关联弱 |
| **重访成本** | 重新打开的难度 | 需登录/多步跳转/会话参数 | 直接 URL 即可重开 |
| **新鲜度** | 最近是否有新发现 | 刚有突破/新内容 | 长期无进展/已读尽 |
| **独特性** | 是否被其他 tab 覆盖 | 唯一来源，不可替代 | 与其他 tab 内容重复 |

### 评分反思（打分时自问）

- 这个 tab 的内容我**真的还需要**吗，还是只是"以防万一"留着？
- 关掉它后**重新打开**要付出什么代价？（登录态丢失？多步导航？）
- 它的信息是否**已经被我提取并记录**在别处了？
- 有没有**另一个 tab 已经覆盖**了它的内容？

### 特殊处理

- **pinned tab 免淘汰**：`tab_manager.py pin <id>` 标记的关键 tab 不参与评分。但 pinned 数量不宜过多（建议 ≤3），否则失去淘汰空间。
- **用户 tab 绝不淘汰**：管理的 tab 才能被 evict。
- **task 标签辅助判断**：`acquire` 时标注的 task 帮助识别哪些 tab 属于已完成的历史任务（可优先淘汰）。

## 常用命令

```bash
# 查看池健康度
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py status

# 开新 tab（达 11 会被拒，提示先淘汰）
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py acquire https://example.com --task "调研XX"

# 列出所有 tab 元数据（达整理线时用于评分决策）
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py list

# 淘汰指定 tab（LLM 选定的最低分者）
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py evict <target_id>

# 标记关键 tab 免淘汰
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py pin <target_id>

# 使用 tab 后更新 lastUsed（辅助未来评分）
python3 ${CLAUDE_SKILL_DIR}/scripts/tab_manager.py touch <target_id>
```

## 与 deep-research-search 的关系

deep-research-search 有自己的 `cdp_client.TabPool`（信号量上限 15），它批量抓取时自己管理 tab 租约（acquire → 用完自动 release）。web-chrome 的 15-tab 池是**面向 agent 交互式浏览**的管理层，两者共享同一个 Chrome 实例和 cdp-proxy，但管理层独立。当 deep-research-search 的子 agent 加载 web-chrome 时，应使用 web-chrome 的 tab_manager 而非自己的 TabPool。
