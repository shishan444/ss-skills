# SubAgent System Prompt 元设计指导手册 v2

> **用途**：指导 AI（或人类）为多Agent系统创作高质量的 SubAgent System Prompt。
> **核心立场**：System Prompt 不是自包含的认知单体，而是四层认知架构中的**编排层**。
> **适用范围**：Claude Code SubAgents、Agent SDK、及所有支持 Rules/Skills 机制的 Agent 框架。

---

## 第一章 · 根本认知：四层认知架构

### 1.1 SubAgent 的认知从何而来

SubAgent 的完整认知由四层构成，每层职责不同、作用域不同、更新频率不同：

```
┌─────────────────────────────────────────────────┐
│  第一层：System Prompt                           │
│  身份、编排逻辑、输出协议                         │
│  作用域：单个 SubAgent 独有 · 更新：很少变动       │
├─────────────────────────────────────────────────┤
│  第二层：Rules / CLAUDE.md                       │
│  项目规范、团队约定、架构决策、编码标准             │
│  作用域：项目内所有 Agent 共享 · 更新：随项目演进   │
├─────────────────────────────────────────────────┤
│  第三层：Skills                                  │
│  领域专业知识、操作流程、最佳实践、检查清单         │
│  作用域：跨项目可复用 · 更新：相对稳定              │
├─────────────────────────────────────────────────┤
│  第四层：Task Prompt（调用时传入）                 │
│  本次任务的具体目标、文件路径、错误信息             │
│  作用域：单次调用 · 更新：每次都变                  │
└─────────────────────────────────────────────────┘
```

### 1.2 System Prompt 的正确定位

System Prompt 是四层的**编排核心**，只负责三件事：

1. 声明"我是谁"（身份锚定）
2. 指明"我如何协调其他三层"（编排逻辑）
3. 定义"我的结果以什么形式交回调用者"（输出协议）

它**不应该**做的事：
- ❌ 内联项目编码规范 → CLAUDE.md 的职责
- ❌ 内联领域检查清单 → Skill 的职责
- ❌ 内联本次任务的文件路径 → Task Prompt 的职责

**核心隐喻**：System Prompt 是指挥家，不是整个乐团。

### 1.3 为什么分层至关重要

全部塞进 System Prompt 的后果：
- Prompt 膨胀到 2000+ tokens，关键指令被淹没（Lost in the Middle）
- 项目规范变更时需修改每个 SubAgent
- 同一知识在多个 SubAgent 中重复，不一致性累积
- 无法跨项目复用

正确分层的收益：
- System Prompt 精炼到 100-400 tokens，每条指令被充分关注
- 项目规范改一处（CLAUDE.md），全部 Agent 同步
- 领域知识改一处（Skill），所有引用者同步升级
- SubAgent 可跨项目迁移——换 CLAUDE.md 即可适配

---

## 第二章 · 四层各自的设计规范

### 2.1 第一层：System Prompt — 身份与编排

内容清单（按顺序）：
1. **身份声明**（1-3句）— 领域、资历、视角、约束倾向
2. **Rules 协同指令**（1句）— "遵循 CLAUDE.md 中的项目规范"
3. **Skills 协同指令**（1-2句）— "参考 {skill} 中的检查清单"
4. **操作协议**（3-7步）— 执行骨架流程，不写具体检查项
5. **输出协议** — 返回给父Agent的固定结构
6. **约束与边界**（2-5条）— 工具限制、行为禁区、不确定时的策略

**Token 预算**：100-400 tokens。超过 400 时，检查是否有内容应归属其他层。

### 2.2 第二层：Rules / CLAUDE.md — 项目共享规则

所有 Agent（含 SubAgent）自动加载。应包含：
编码规范、命名约定、架构决策、依赖管理、测试要求、提交规范、安全规则。

不应包含：某 SubAgent 独有逻辑（→ System Prompt）、可复用领域知识（→ Skill）、单次任务上下文（→ Task Prompt）。

**冲突处理**：System Prompt 与 CLAUDE.md 冲突时，需在 System Prompt 中显式声明覆盖关系。

### 2.3 第三层：Skills — 可复用的领域知识

Skill 是跨项目复用的知识模块——SubAgent 的"专业教材"。典型内容：领域检查清单、操作流程详解、最佳实践集合、输出模板库、工具使用指南。

**推荐结构**：
```markdown
# SKILL.md
## 概述（一句话能力说明）
## 何时使用（触发条件）
## 知识内容（检查清单/操作流程/最佳实践）
## 输出建议（推荐输出结构）
```

**System Prompt 引用方式**：
```markdown
直接引用:  执行审查时，参考 security-audit Skill 中的检查清单。
条件引用:  如果发现性能问题，参考 performance-optimization Skill。
多Skill:   依次参考 code-quality Skill 和 security-audit Skill。
```

### 2.4 第四层：Task Prompt — 单次调用上下文

父Agent调用时传入的动态指令：具体目标、文件路径、错误信息、决策上下文、范围约束。

Task Prompt 是父Agent→SubAgent 的唯一动态通道。SubAgent 上下文窗口全新，所有"这次做什么"必须显式传入。

---

## 第三章 · System Prompt 六条设计原则

### 原则一：薄编排层

每个 token 只回答"身份/流程/输出"。领域知识指向 Skill，项目规范指向 CLAUDE.md。

**自检**：逐句问"删掉这句后，能否通过其他层提供等效信息？"能则移出。

### 原则二：单一职责

每个 SubAgent 只解决一类问题。description 中出现"和"连接不同能力时，应拆分。
```
❌ "审查代码并修复问题" → 两个角色混合
✅ "审查代码，输出问题清单" + "根据报告修复代码" → 拆为两个
```

### 原则三：显式层间引用

System Prompt 必须显式声明与其他层的协同关系：
```markdown
## 项目规范
遵循 CLAUDE.md 中的编码标准。冲突时以本指令为准（仅限工具权限和输出格式）。
## 领域知识
参考 security-audit Skill。Skill 与 CLAUDE.md 冲突时以 CLAUDE.md 为准。
```
**默认优先级序**：System Prompt > CLAUDE.md > Skill > Task Prompt 建议

### 原则四：输出面向调用者

父Agent只收到最终消息（中间工具调用不返回）。因此：结构固定可预测、包含枚举值判定（PASS/FAIL/NEEDS_REVIEW）、关键证据完整呈现。

### 原则五：工具最小权限
```yaml
只读探索:    Read, Grep, Glob
只读审查:    Read, Grep, Glob, Bash
实现/修复:   Read, Write, Edit, Bash, Grep, Glob
```
需要 Bash 时进一步约束允许/禁止的命令类别。

### 原则六：防御性边界

- **信息不足**：报告缺什么，不猜测
- **超出职责**：声明边界，列出但不解决
- **不确定**：标记 NEEDS_REVIEW，附原因

---

## 第四章 · Description 设计

### 4.1 三要素公式

```
description = 能力声明 + 触发条件 + 排除条件（可选）
```
```yaml
❌  帮助处理代码
❌  专业的安全代码审查工具
✅  安全代码审查专家。代码编写或修改后立即调用。只读，不修改文件。不处理性能问题。
```

### 4.2 多 SubAgent 路由去重
```yaml
❌ reviewer: "处理代码问题"   fixer: "修复代码缺陷"         # 模糊重叠
✅ reviewer: "只读审查，输出清单"  fixer: "根据报告修复代码"  # 边界清晰
```

---

## 第五章 · 完整示例：四层协同

### 5.1 代码审查 SubAgent

**System Prompt（~200 tokens）**：
```markdown
---
name: code-reviewer
description: >
  高级代码审查专家。代码编写或修改后立即调用。只读，不修改文件。
tools: Read, Grep, Glob, Bash
model: inherit
---
你是一位资深代码审查工程师。

## 项目规范
遵循 CLAUDE.md 中的编码标准和架构约定。

## 领域知识
执行审查时，参考 code-review Skill 中的检查维度和评判标准。

## 执行流程
1. 运行 `git diff` 确定变更范围
2. 逐文件按 Skill 检查维度审查
3. 汇总生成报告

## 输出协议
### 判定：PASS | FAIL | NEEDS_REVIEW
### 摘要：变更文件数、问题数、严重程度分布（🔴🟡🟢）
### 发现明细：每个问题含文件、行号、类别、严重程度、描述、建议

## 约束
- 绝不修改文件
- 不确定标记 NEEDS_REVIEW
- 不评价风格偏好
```

**配套 code-review Skill（~300 tokens）**：
```markdown
# code-review Skill
## 安全性：SQL注入、XSS、认证缺陷、信息泄露、SSRF
## 性能：N+1查询、缺索引、同步阻塞、内存泄漏、未缓存重复计算
## 可维护性：函数>50行、圈复杂度>10、命名不清、重复代码≥3处、静默吞异常
## 测试：新逻辑无测试、边界未覆盖、过度Mock
## 严重程度
- 🔴 高：可利用安全漏洞或必然数据丢失
- 🟡 中：性能隐患、可维护性、非关键安全
- 🟢 低：改进建议
```

**配套 CLAUDE.md（项目级共享）**：
```markdown
## 技术栈：TypeScript 5.x + React 18 + Node 20 + PostgreSQL 16
## 编码标准：严格模式，禁止any，zod校验，Result<T,E>错误处理
## 架构：controller→service→repository，禁止跨层
## 测试：vitest，覆盖率≥80%
```

**Task Prompt（每次不同）**：
```
审查 src/auth/login.ts 的最近变更。Session→JWT替换，关注token验证和密钥管理。PR #342。
```

### 5.2 探索型 SubAgent（极简）

```markdown
---
name: explorer
description: 快速代码库搜索分析。需理解代码结构或定位实现时调用。只读。
tools: Read, Grep, Glob, Bash
model: haiku
---
你是代码库探索专家。

## 项目规范
参考 CLAUDE.md 了解目录结构和技术栈。

## 执行流程
1. 根据目标确定搜索策略
2. Glob定位 → Grep搜索 → Read查看
3. 搜索彻底，不遗漏相关目录

## 输出
简洁直接。关键文件+一句话说明。未找到时说明已搜索范围。
```

不到 120 tokens。不需要 Skill。目录结构由 CLAUDE.md 提供。

### 5.3 架构师 SubAgent（多 Skill 协同）

```markdown
---
name: architect
description: 系统架构评审。功能设计或重大重构前调用。只读，不实施变更。
tools: Read, Grep, Glob, Bash
model: inherit
---
你是资深系统架构师。

## 项目规范
严格遵循 CLAUDE.md 中的架构约定和技术栈。

## 领域知识
- 可扩展性 → scalability-patterns Skill
- 数据层 → database-design Skill
- API → api-design Skill

## 执行流程
1. 理解需求 2. 探索现有模块 3. 评估兼容性 4. 识别风险 5. 输出建议

## 输出协议
### 结论：APPROVE | REVISE | REJECT
### 评估：兼容性/可扩展性/性能/安全（各高/中/低）
### 建议 + 风险及缓解策略

## 约束
- 不实施变更 · 建议限于 CLAUDE.md 技术栈 · 超出能力时明确声明
```

---

## 第六章 · 反模式与修正

### 反模式一：知识内联
System Prompt 内写了 30 条检查规则。→ 检查规则移入 Skill，编码规范确认在 CLAUDE.md。

### 反模式二：隐式依赖
写"按我们的标准"不指明来源。→ 显式写"遵循 CLAUDE.md"或"参考 X Skill"。

### 反模式三：层间混淆
**归位判断树**：
```
只属于一个 SubAgent？ → System Prompt
特定于当前项目？     → CLAUDE.md
每次调用都不同？     → Task Prompt
以上都不是？         → Skill
```

### 反模式四：万能 SubAgent
同时审查、修复、测试、写文档。→ 按职责拆为流水线。

### 反模式五：输出无判定
返回"整体还不错"。→ 要求枚举判定 + 触发条件定义。

### 反模式六：Skill 不更新
创建后从未维护。→ 加版本标记和更新日期，定期审查。

---

## 第七章 · 进阶编排模式

### 7.1 链式调度
```
PM-Spec → Architect → Implementer → Reviewer → Verifier
```
每个节点定义输入预期和输出协议。Skill 和 CLAUDE.md 全链共享。

### 7.2 并行扇出
```
父Agent ─┬─ Reviewer-A(模块A) ─┐
          ├─ Reviewer-B(模块B) ─┤─ 汇总
          └─ Reviewer-C(模块C) ─┘
```
同 System Prompt + 同 Skill，差异仅在 Task Prompt。

### 7.3 模型降级
搜索/格式化 → `haiku`（快）。标准工作 → `inherit`。深度判断 → `opus`（强）。

### 7.4 Skill 组合
一个 SubAgent 引用多个 Skill，各维度独立子判定，最终取最严格值。

---

## 第八章 · 质量检查清单

### 分层正确性
- [ ] System Prompt ≤ 400 tokens？
- [ ] 项目规范在 CLAUDE.md 中？领域清单在 Skill 中？动态信息留给 Task Prompt？

### 层间协同
- [ ] 显式引用 CLAUDE.md 和所需 Skill？冲突时有优先级声明？

### 单一职责
- [ ] description 无"和"连接不同能力？工具列表最小必要？

### 输出可靠性
- [ ] 固定结构 + 枚举判定 + 关键信息完整？

### 防御性
- [ ] 信息不足/超出职责/不确定 各有策略？

---

## 附录 · 速查模板

```markdown
---
name: {kebab-case}
description: {能力}。{触发条件}。{排除条件}。
tools: {最小工具集}
model: {haiku | inherit | opus}
---
你是一位 {领域} 的 {资历} 专家。{一句话约束}。

## 项目规范
遵循 CLAUDE.md 中的 {具体引用}。

## 领域知识
参考 {skill-name} Skill 中的 {具体引用}。

## 执行流程
1. {步骤}  2. {步骤}  3. ...

## 输出协议
### 判定：{枚举值}
### 摘要：{要求}
### 详情：{结构}

## 约束
- 绝不 {禁止行为}
- {边界情况} 时 {策略}
```

---

> **设计的本质**：
> System Prompt 是指挥家，CLAUDE.md 是乐谱，Skill 是演奏技法，Task Prompt 是今晚的曲目。
> 指挥家不需要记住每个音符——他需要知道何时让谁演奏、以什么节奏、达到什么效果。