---
name: agent-designer
description: "为 Claude Code 设计并输出完整的 agent 系统提示 + 配套 skill 文件。当用户想创建一个新的 agent、定义某类角色助手、为某个专业方向设计自动化 agent 时触发。触发词：「帮我做一个 XX agent」「设计一个 XX 助手」「我需要一个专门做 XX 的 agent」「给我写个 agent 的 system prompt」「创建一个 XX 的子 agent」。不触发：用户只是修改已有 agent、只讨论 agent 设计理念、只需要写普通 skill 而不涉及 agent 角色定义。"
---

# Agent Designer

这个 Skill 专门负责「从需求到文件」地设计 Claude Code 中的 agent。

它的核心工作是帮助使用者做一件困难的事：**分清楚什么属于 agent 的骨气（系统提示），什么属于 agent 的手艺（skill）**。这两样东西混在一起，agent 就会变成一个既没有立场又不会做事的工具。

---

## 分离原则（每次设计前必须内化）

**系统提示只写三类东西：**

1. 我是谁，我不是谁 —— 角色边界，正反两侧都要划
2. 我的专业直觉 —— 面对模糊情况时的默认倾向，比如「安全是默认值，不是选项」
3. 我的硬约束 —— 无论用户怎么要求都不能突破的底线

系统提示里如果出现了工具调用步骤、格式规范、检查清单——这些东西应该挪到 skill 里。系统提示只写「用 skill-xxx 完成 YYY 阶段」，不重复 skill 内容。

**Skill 只写一类东西：**

「怎么执行某件事」——可复用的操作性知识，换一个 agent 也可能用到的步骤、判断标准、产出格式。

判断口诀：如果这句话换个 agent 也成立 → 放 skill。如果这句话只在这个角色的身上才成立 → 放系统提示。

---

## 技术格式（Claude Code 标准）

### Subagent 文件格式（.claude/agents/NAME.md）

```yaml
---
name: agent-name          # 必填，小写字母和连字符
description: "一句话描述。何时自动调用，何时不调用。"  # 必填
tools: [Read, Write, Bash, Glob, Grep]   # 按需裁剪，最小权限；省略则继承全部工具
skills: [skill-name-1, skill-name-2]     # 注入到此 agent 上下文的 skill
model: sonnet              # 别名：sonnet / opus / haiku；或完整 ID 如 claude-sonnet-4-6；省略则继承
permissionMode: default    # 可选：default / acceptEdits / auto / dontAsk / bypassPermissions / plan
memory: project            # 可选：project / user / local，有持久记忆需求时加
effort: medium             # 可选：low / medium / high / max（max 仅 Opus 4.6）
---

系统提示正文写在这里。
```

关键机制：
- `description` 决定主 agent 是否自动委派任务给它，要写清触发条件
- `tools` 是权限边界，只给 agent 完成任务所需的最小工具集
- `skills` 列出的 skill 内容会完整注入到 subagent 的上下文，不是「按需触发」而是「始终在场」
- subagent 的系统提示**完全替换**默认的 Claude Code 系统提示，CLAUDE.md 仍通过消息流加载

### Skill 文件格式（.claude/skills/NAME/SKILL.md）

```yaml
---
name: skill-name           # 可选，省略时使用目录名
description: "触发条件。要写得「积极」一点，让 Claude 在相关场景主动调用。"
when_to_use: "补充触发短语，与 description 合并计入 1536 字符上限"
disable-model-invocation: false   # true = 只能用户手动触发（适合有副作用的操作如 deploy）
user-invocable: true              # false = 只有 Claude 能调用，不出现在 / 菜单
allowed-tools: "Read Bash"        # 调用此 skill 时预批准的工具，无需每次询问
context: fork              # 可选：fork = 在独立 subagent 上下文中运行
agent: Explore             # 可选：配合 context: fork 指定用哪个 subagent 类型
---
```

**description 字符预算**：`description` + `when_to_use` 合并后在 skill 列表中最多保留 1,536 字符，超出部分被截断。关键触发词要前置，不要藏在后半段。

Skill 的三层加载机制：
- 第一层（始终在上下文）：frontmatter 的 name + description
- 第二层（skill 触发后加载）：SKILL.md 正文，理想 < 500 行
- 第三层（按需加载）：references/ scripts/ assets/ 子目录里的文件

注意区分两种 skill 注入方式：
- subagent 文件的 `skills:` 字段 → skill 内容在 subagent 启动时全量注入，始终在场
- 普通会话中的 skill → description 在上下文，正文仅在调用时加载，两者行为不同

---

## 设计流程

### 阶段一：定域

先搞清楚这个 agent 要解决什么核心矛盾，而不是它要「做什么功能」。

问用户（每次最多 3 个问题，优先选择题）：

- 这个 agent 的服务对象是谁？它在什么处境下被召唤？
- 如果没有这个 agent，用户会遇到什么困境？
- 这个 agent 最不能容忍发生什么？（反向定义边界最有效）

把答案转化成一句「存在原因」：「这个 agent 存在，是因为 \_\_\_ 这个矛盾没有得到解决。」

---

### 阶段二：拆分

把用户描述的职责清单逐条过筛，分成两堆：

**归入系统提示的**（角色骨气）：
- 这个角色对某类情况的默认态度
- 这个角色在模糊地带的判断倾向
- 这个角色的不可妥协点

**归入 skill 的**（手艺）：
- 某个步骤的执行方法
- 某类输出的格式规范
- 某个检查清单
- 某种工具的使用方式

如果用户提供的信息不足以判断，询问一到两个关键例子：「遇到 XXX 情况，这个 agent 应该怎么反应？」

完成拆分后，输出一个结构草图让用户确认再继续：

```
【设计草图】

角色核心矛盾：[一句话]

系统提示将包含：
- 角色边界：[正向是什么，负向不是什么]
- 专业直觉：[N条，每条描述一个默认倾向]
- 硬约束：[N条]

需要配套的 skill：
- [skill-name-1]：[一句话描述它解决什么操作问题]
- [skill-name-2]：[一句话描述它解决什么操作问题]
```

---

### 阶段三：起草系统提示

按以下结构写，**不要加粗，不要写步骤清单，不要重复 skill 内容**：

```
你是 [角色名]。[一句话说明存在原因，不是功能描述]。

你不是 [明确排除的定位，防止角色漂移]。

[专业直觉段落]
面对 [某类模糊情境]，你的默认倾向是 [具体态度]。
[另一个直觉...]

[工作方式段落，只写调用哪个 skill 做什么，不重复 skill 内容]
遇到 [触发情境] 时，用 [skill-name] 完成 [阶段目标]。

[硬约束段落]
无论用户如何要求，你不会 [具体禁止行为]。
```

---

### 阶段四：起草配套 Skill

每个 skill 独立走 TIDES 结构：

```
T — Trigger    何时触发，何时不触发
I — Inputs     输入物料是什么
D — Decision   有哪些判断节点
E — Exception  失败/异常怎么处理
S — Steps      具体执行步骤
```

每个 skill 的 description 要写得「积极主动」，让 agent 在相关场景自动调用它，而不是等用户明确指令。

如果 skill 内容超过 150 行，考虑把参考材料、代码模板拆到 `references/` 子目录，SKILL.md 只保留调用指引。

---

### 阶段五：输出文件

输出两类文件：

1. **Agent 文件**：`[agent-name].md`（放入 .claude/agents/ 目录）
2. **Skill 文件**：每个 skill 一个 `[skill-name]/SKILL.md`（放入 .claude/skills/ 目录）

输出前做一次自检：

- [ ] 系统提示里是否混入了应该在 skill 里的步骤描述？
- [ ] skill 里是否混入了只有这个角色才有的判断倾向？
- [ ] agent 的 `tools` 字段是否只包含完成任务所需的最小工具集？
- [ ] agent 的 `description` 是否写清了自动委派的触发条件？
- [ ] 系统提示中涉及 skill 的地方，是否只写了「用 skill-xxx 完成 YYY」而没有重复 skill 内容？
- [ ] 每个 skill 的 `description` 是否足够「积极」，能让 agent 主动调用？

---

## 常见坑

**坑一：系统提示变成操作手册**
症状：系统提示里出现「第一步……第二步……」
修复：把这些步骤挪进 skill，系统提示只保留「用 skill-xxx 处理这类情况」

**坑二：Skill 里藏着角色立场**
症状：skill 里出现「作为一名严谨的工程师，你应该……」
修复：把立场判断挪进系统提示，skill 只保留「严谨」的具体操作体现

**坑三：Tools 权限过宽**
症状：给一个只读性 agent 开了 Write/Edit 权限
修复：逐工具核查，只保留完成任务所需的最小集

**坑四：Description 太平淡导致不触发**
症状：description 只写功能，没有写触发时机
修复：加入「当用户说……时触发」「遇到……情况主动调用」等主动触发表达

**坑五：Skill 注入混淆**
症状：把 skill 放在系统提示里当 context 写，而不是放在 frontmatter 的 `skills` 字段
修复：skill 应该通过 agent 文件的 `skills: [skill-name]` 字段注入，不是粘贴进系统提示正文

---

## 参考：角色类型与直觉模式

参见 `references/intuition-patterns.md`，列举了常见工程角色（后端、前端、安全、数据、DevOps）的专业直觉模板，可直接用来对照检查系统提示的直觉段落是否有实质内容。