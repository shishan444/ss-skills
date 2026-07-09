# 小说创作Agent Teams流水线设计

## 架构概览

```
default（大脑/编排者）
├── 和用户对话：创意方向、题材选择、流程决策
├── 任务分解：把小说创作拆成Kanban卡片
├── 观察调度：监控worker进度，灵活调度
├── review循环决策：判断需不需要下一轮review
└── 交付汇报：向用户报告结果
      │
      ▼
novel-writer（写手）     novel-reviewer（审稿员）    novel-editor（润色编辑）
├── 章节写作              ├── novel-stage-review八维审计 ├── 润色（断句/排版/文风）
├── P0/P1修复              ├── P0/P1/P2分级             ├── 整理（合并/归集/清理）
└── 标识符修复             ├── 写入review.md             └── 更新progress.json
```

## 数据共享

所有worker共享同一个小说目录：`stories/{novel-id}/`

- novel-writer 读写 `drafts/chapter-XX.md`
- novel-reviewer 读 `drafts/` + 设定文件，写 `review.md`
- novel-editor 读写 `drafts/` + 合并文件 + `progress.json`

Worker的工作区（workspace）指向小说目录，确保所有操作在同一份文件上。

## Kanban卡片流程

### 核心原则：串行写作 + 阶段性设定review

1. **章节严格串行**：Ch1完→Ch2→Ch3...不并行。每章的上下文连贯，避免一致性问题。
2. **每个Act完成后做设定review**：检查世界观/人物/关系/剧情链路是否需要更新，防止跑题。
3. **每个Act完成后做质量review**：使用 `novel-stage-review` 八维审计，包含情绪路由兑现和冷启动追读检查。
4. **全部写完后做完整review**：沿用 `novel-stage-review` 的P0/P1/P2分级，修复循环到收敛。

### 一部小说从构思到完成

```
Phase 0: 构思（default直接做，不创建卡片）
  - 创意入口生成器产出方案
  - 和用户确认
  - 创建 concept.md / tone-guide.md / emotion-style-map.md / front-30-hook-map.md / characters.md / character-ledger.md / worldbuilding.md / outline.md / writing-guide.md / foreshadow-tracker.md / expectation-list.md
  - outline每个关键节点必须有：剧情功能 / 读者期待 / 目标体感 / 呈现模式 / 爽点阶段 / 章长策略
  - front-30-hook-map必须定义：前三章冷启动职责 / 前30章短钩子 / 中钩子 / 长钩子

Phase 1: 初稿（串行写作 + 阶段设定review）

  ┌─ Act 1: Ch1-Ch12 ──────────────────────────────┐
  │                                                  │
  │  Card: "写作：Ch1"                                │
  │    assignee: novel-writer                        │
  │    workspace: dir:stories/{novel-id}             │
  │    parents: []                                   │
  │                                                  │
  │  Card: "写作：Ch2"                                │
  │    parents: [Ch1卡]                              │
  │                                                  │
  │  ... Ch3, Ch4, ... Ch12（严格串行，每章依赖前一章）│
  │                                                  │
  │  Card: "阶段设定review：Act 1"                     │
  │    assignee: novel-reviewer                      │
  │    parents: [Ch12卡]                             │
  │    → 执行 novel-stage-review：                      │
  │      - 世界观：新地点/新规则/偏移？                  │
  │      - 人物：新角色/行为一致性？                    │
  │      - 关系：人物关系变化？                        │
  │      - 剧情链路：大纲是否需要调整？                  │
  │      - 情绪路由：目标体感/呈现模式/爽点阶段/章长策略是否兑现？ │
  │      - 冷启动追读：前三章/前30章钩子是否兑现？          │
  │    → 输出：P0/P1/P2问题、设定更新建议、情绪路由和追读钩子修复建议 │
  │                                                  │
  │  Card: "设定更新：Act 1"                           │
  │    assignee: novel-writer（或default直接做）       │
  │    parents: [阶段设定review卡]                     │
  │    → 按建议更新设定文件                             │
  │                                                  │
  └──────────────────────────────────────────────────┘

  ┌─ Act 2: Ch13-Ch25 ─────────────────────────────┐
  │  同上结构：Ch13→Ch14→...→Ch25（串行）             │
  │  → 阶段设定review                                 │
  │  → 设定更新                                       │
  └──────────────────────────────────────────────────┘

  ... Act 3, Act 4, Act 5 同上 ...

  ┌─ 完整Review循环 ────────────────────────────────┐
  │                                                  │
  │  全部章节写完后：                                   │
  │                                                  │
  │  Card: "完整Review第1轮"                           │
  │    assignee: novel-reviewer                      │
  │    → novel-stage-review八维审计                    │
  │    → 写入review.md                                │
  │    → summary: P0=X, P1=Y, P2=Z                  │
  │                                                  │
  │  [default判断：P0/P1 > 0？]                       │
  │    是 → 创建修复卡 + 验证卡                         │
  │    否 → 初稿阶段完成                               │
  │                                                  │
  │  Card: "修复P0/P1"                                │
  │    assignee: novel-writer                        │
  │    → 按review.md修复                              │
  │                                                  │
  │  Card: "验证修复"                                  │
  │    assignee: novel-reviewer                      │
  │    → 验证修复是否到位、有无新问题                     │
  │                                                  │
  │  [default判断：P0/P1 > 0？]                       │
  │    是 → 创建新Review卡（第2轮），循环               │
  │    否 → 初稿阶段完成                               │
  │                                                  │
  └──────────────────────────────────────────────────┘

Phase 2: 润色
  Card: "润色"
    assignee: novel-editor
    parents: [最后一个验证卡]
    → editor执行润色

Phase 3: 整理
  Card: "整理归档"
    assignee: novel-editor
    parents: [润色卡]
    → editor合并文件、归集设定、更新progress.json
```

## review循环的退出条件

review.md中的最后一轮必须满足：
```
### 第N轮
- P0: 0
- P1: 0
- P2: 可有可无（不影响退出）
- 结论：初稿阶段完成，可进入润色
```

## default（大脑）的职责清单

1. **构思阶段**：直接做，不委派。产出设定文件。
2. **写作阶段**：创建写作卡片分配给novel-writer。章节必须串行；下一章必须依赖上一章的完成状态、角色账本和情绪路由卡。
3. **Review阶段**：创建Review卡分配给novel-reviewer，按 `novel-stage-review` 做八维审计。等结果回来后做判断。
4. **修复阶段**：如果P0/P1>0，创建修复卡分配给novel-writer。
5. **验证阶段**：创建验证卡分配给novel-reviewer。
6. **循环判断**：每一轮验证后，读review.md的最新轮次。P0/P1=0才解锁润色。
7. **润色阶段**：创建润色卡分配给novel-editor。
8. **整理阶段**：创建整理卡分配给novel-editor。
9. **交付**：确认整理完成后，向用户汇报。
10. **灵活调度**：如果worker卡住/超时，重新分配或自己接管。

## 并行限制

同一时间最多推进一部小说的全流程。一部走完全部阶段，才能开下一部。
一部小说内部不得并行写多个章节；可并行的只包括不改正文的只读审计、资料整理、定量扫描等辅助任务。正文写作、P0/P1修复和章节级情绪路由必须按章节顺序串行推进。
