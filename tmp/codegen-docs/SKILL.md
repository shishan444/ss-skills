---
name: codegen-docs
description: 为工程代码生成文档骨架，便于后续LLM 讨论需求和架构设计方案
disable-model-invocation: true
---

# Codegen Docs — 工程细节描述文档生成与维护

## 做什么

当用户手动触发并指定工程根目录路径时，为该工程生成或更新一套按四层结构（地图层/领域层/横切层/流程层）组织的工程细节描述文档，存放在 docs/ 目录下。校验报告存放在 docs/validation/ 下。

**技术栈范围**：前端 Web（React / Vue / Next.js / Angular）+ 后端 Python（Django / Flask / FastAPI / Tornado）。

不触发：非工程级文档生成/更新任务；技术栈不在覆盖范围内的工程。

## 怎么做

### Step 0：模式判定

检测 docs/ 目录是否已存在且包含有效的地图层文档（MAP.md）。
  - 不存在或无效 → 进入「首次生成」流程（Step 1-9）
  - 已存在且有效 → 进入「文档更新」流程（Step 10-15）

---

### 首次生成流程

#### Step 1：工程全景扫描

扫描工程根目录结构，识别：
  - 是否为 monorepo / 单项目 / 多模块
  - 技术栈（语言、框架、构建工具、包管理器）
  - 工程类型分区——判断工程中包含哪些分区（前端 Web / 后端 Python / 混合），确定 docs/ 下需要创建哪些子目录

分区判定策略查阅 `references/module-discovery.md` 的「工程类型分区判定」章节。

构建 docs/ 目录结构：
```
docs/
  MAP.md
  {类型分区}/
    domain/
      {模块名}.md
    crosscut/
      {关注点名}.md
    flows/
      {流程名}.md
    INDEX.yaml
  validation/
    {日期}-generate.md
```

单一分区工程（仅前端或仅后端）：docs/ 下直接存放 domain/、crosscut/、flows/、INDEX.yaml，不创建分区子目录。

混合分区工程：创建 docs/backend/ 和 docs/frontend/ 两个分区子目录。

#### Step 2：模块发现（互补合并）

三层探测互补执行，结果合并。详细策略查阅 `references/module-discovery.md`。

  **2a. 声明式信号扫描**
  - 前端 Web 信号：React Router 路由配置、Vue Router 配置、Next.js app/pages 目录、Angular module 定义
  - 后端 Python 信号：Django apps.py、Flask Blueprint、FastAPI APIRouter、Tornado Application handlers
  - Monorepo 信号：pnpm-workspace.yaml、lerna.json、turborepo 配置

  提取到的模块标记为「声明式·高置信度」。

  **2b. 依赖聚类分析（对 2a 未覆盖的文件执行）**
  - Python：分析 from/import 语句，按依赖聚集性聚类
  - 前端：分析 import/require 语句，按引用关系聚类
  - 粒度阈值：< 3 文件的簇合并到最近关联簇，> 30 文件的簇按子目录拆分

  提取到的模块标记为「依赖聚类·待确认」。

  **2c. 目录兜底（对 2b 仍未覆盖的文件执行）**
  - 按一级子目录切分
  - 排除非业务目录（完整过滤清单见 `references/module-discovery.md`）
  - 提取到的模块标记为「目录推断·待确认」

  **合并**：三层结果合并为最终模块清单，去重。模块清单中每个模块标注发现方式。

#### Step 3：生成地图层文档

输出 `docs/MAP.md`，按 `references/templates.md` 中「地图层模板」生成。包含：
  - 工程概述（是什么、做什么、不做什么）
  - 技术栈与架构风格
  - 工程类型分区说明
  - 模块清单（名称、职责简述、边界、源码路径、发现方式）
  - 模块间依赖关系（Mermaid 有向图）
  - 关键约束（部署环境、性能基线、合规要求等）
  - 生成时间戳 + git commit hash

  约束：控制在 500-800 token 以内。

#### Step 4：提交地图层供人类确认

  - 将 MAP.md 内容展示给用户
  - 用户可调整模块划分、边界、命名
  - 获得明确确认后继续；未确认则等待

  约束：此步骤不可跳过。未获得人类确认不得进入 Step 5。

#### Step 5：生成领域层文档（Layer 1）

按确认后的模块清单，逐模块生成文档。每个模块输出一个文件至 `docs/{类型分区}/domain/{模块名}.md`，按 `references/templates.md` 中「领域层模板」生成。采用「固定骨架 + 可选 Section」模式——必选 Section 不可省略，可选 Section 按启用条件判断。

  约束：
  - 每个文档控制在 800-1500 token
  - 单次上下文无法装载所有模块时，按模块逐个分片执行——每生成一个即保存，再处理下一个
  - 发现方式为「目录推断·待确认」的模块，在文档头部添加自动推断标注

#### Step 6：生成横切层文档（Layer 2）

扫描识别横切关注点，每个关注点输出一个文件至 `docs/{类型分区}/crosscut/{关注点名}.md`，按 `references/templates.md` 中「横切层模板」生成。

  横切关注点识别策略查阅 `references/crosscut-strategy.md`。包含三重信号扫描：依赖扫描 + import 扫描 + 文件/目录扫描。按优先级 P1 > P2 > P3 生成。

#### Step 7：生成流程层文档（Layer 3）

从入口点追踪端到端数据流转，每个流程输出一个文件至 `docs/{类型分区}/flows/{流程名}.md`，按 `references/templates.md` 中「流程层模板」生成。包含：
  - 流程触发入口
  - 数据流经的模块序列（Mermaid sequenceDiagram）
  - 每个节点的数据转换规则
  - 状态变迁链

  入口点识别与流程筛选策略查阅 `references/flow-strategy.md`。按 P1（核心业务）/ P2（异常降级）/ P3（管理运维）优先级筛选，排除纯 CRUD 和静态页面。

#### Step 8：生成索引文件

为每个类型分区目录生成 `INDEX.yaml`，按 `references/templates.md` 中「索引文件 Schema」生成。包含：
  - 源码路径 → 文档路径的映射
  - 契约类型（接口/事件/数据结构）→ 文档章节的映射
  - 生成元数据（时间戳、commit hash、文档版本）

#### Step 9：结构性校验

对生成的文档执行结构性检查（非语义校验）：
  - 必选 Section 是否齐全
  - 源码锚点指向的文件是否存在
  - 模块依赖列表中的模块是否都有对应文档
  - 索引文件与实际文档文件是否一一对应

  生成校验报告至 `docs/validation/{日期}-generate.md`，按 `references/templates.md` 中「首次生成校验报告模板」生成。

---

### 文档更新流程

#### Step 10：变更检测

  - 从 MAP.md 读取上次生成的 git commit hash
  - 执行 git diff，获取变更文件列表
  - 通过索引文件将变更文件映射到受影响的文档切片

#### Step 11：校验 A — 代码 ↔ 设计方案（可选）

  - 检测设计方案文件（预期存放在 docs/designs/ 或用户指定位置）
  - **找到设计方案时**：
    - 逐条对比设计方案的每个变更点是否在代码中落实
    - 识别三类偏差：已落实、遗漏（设计方案有但代码无）、超范围（代码有但设计方案无）
  - **未找到设计方案时**：跳过此步骤，直接进入 Step 12

  `[待完善：设计方案的标准格式要求——最低要求为 Markdown 格式，每个变更点有明确的标题行（## 或 ###），以便 Skill 能结构化解析。后续可根据团队实践细化。]`

#### Step 12：确定受影响范围

  - 根据变更检测结果确定直接受影响的模块列表
  - 通过索引文件的依赖关系检查是否有级联影响
  - 合并直接受影响和级联受影响的模块，形成最终更新范围

#### Step 13：更新受影响的文档切片

  - 按模块逐个重新生成领域层文档（同 Step 5 的模板和约束）
  - 如横切层或流程层受影响，同步更新（同 Step 6/7）
  - 更新索引文件
  - 更新 MAP.md 中的时间戳和 commit hash

#### Step 14：校验 B — 代码 ↔ 文档（深度一致性）

  - 逐模块（按 Step 12 确定的范围）对比更新后的文档与代码实际行为：
    - 接口签名 → 检查路由定义 / 类型声明
    - 数据模型字段 → 检查类型定义 / ORM schema
    - 模块依赖 → 检查 import 关系
    - 业务规则 → 检查代码中的条件判断逻辑
  - 对依赖模块做轻量检查：其文档中对被更新模块的引用是否仍准确
  - 不一致处标注「待确认」

#### Step 15：生成校验报告

  - 汇总校验 A（Step 11，如执行）和校验 B（Step 14）的结果
  - 输出至 `docs/validation/{日期}-update.md`，按 `references/templates.md` 中「更新校验报告模板」生成

---

## 完善指引

1. [中] Step 11 设计方案格式标准 —— 当前仅要求 Markdown + 明确标题行，可按团队实践细化（如约定变更点模板、增加状态标注等）。补全后：设计方案校验能更精准匹配代码变更。

2. [低] 各框架声明式信号扫描的边界 case —— 当前覆盖主流框架的标准项目结构，非标准结构（如自研脚手架、非典型目录组织）需要扩展信号规则。补全方式：在实际工程执行中遇到遗漏时逐条补充到 `references/module-discovery.md`。

---

## 不可破

- 仅手动触发，禁止自动触发
- 唯一输入为工程根目录路径（设计方案路径为可选输入）
- 技术栈范围：前端 Web（React/Vue/Next.js/Angular）+ 后端 Python（Django/Flask/FastAPI/Tornado）。超出范围的工程不执行
- 地图层（MAP.md）必须经人类确认后才能生成二三层文档
- 文档使用建造者视角、自然流畅中文撰写
- 颗粒度判断标准：去掉这条信息会不会改变评估结论
- 单次上下文无法装载时必须分片执行，每生成一个切片即保存再执行下一个
- 校验报告存放在 docs/validation/ 下
