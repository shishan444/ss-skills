---
查阅条件：Step 1 工程类型分区判定、Step 2 模块发现的三层探测策略执行时查阅。
---

# 模块发现策略

本文件定义 codegen-docs 的工程类型分区判定规则和三层模块探测互补合并策略。

---

## 工程类型分区判定

### 判定决策树

```
1. 检测 Monorepo 信号
   ├── 存在 pnpm-workspace.yaml / lerna.json / turborepo.json / nx.json
   │   → Monorepo，每个 workspace 子目录独立执行后续判定
   └── 不存在 → 继续步骤 2

2. 检测后端 Python 信号
   ├── 存在 requirements.txt / pyproject.toml / setup.py / Pipfile
   ├── 存在 manage.py（Django 特征）
   ├── 存在 *.py 文件且 import fastapi / flask / django / tornado
   ├── 存在包含 __init__.py 的 app/ 或 src/ 目录
   │   → 识别为后端 Python 分区
   └── 不满足 → 无后端 Python 分区

3. 检测前端 Web 信号
   ├── 存在 package.json + dependencies 包含 react / vue / next / @angular/core
   ├── 存在 next.config.js/mjs/ts / vue.config.js / angular.json / vite.config.*
   ├── 存在 src/ 或 app/ 目录且包含 .jsx / .tsx / .vue 文件
   ├── 存在 public/ 或 static/ 目录且包含 index.html
   │   → 识别为前端 Web 分区
   └── 不满足 → 无前端 Web 分区

4. 合并结果
   ├── 仅后端 Python → 单分区
   ├── 仅前端 Web → 单分区
   ├── 两者都有 → 混合分区（分别创建 docs/backend/ 和 docs/frontend/）
   └── 都没有 → 不在 Skill 覆盖范围内，提示用户
```

### 分区目录命名

| 分区类型 | docs/ 子目录 |
|----------|-------------|
| 单一后端 Python | docs/（直接存放，无分区子目录）|
| 单一前端 Web | docs/（直接存放，无分区子目录）|
| 混合 | docs/backend/ + docs/frontend/ |
| Monorepo | 每个 workspace 独立判定 |

---

## 声明式信号扫描（2a）

### 前端 Web 框架

#### React

**检测信号**：package.json 中 dependencies 包含 "react"

**模块提取**：
- 路由配置：扫描 src/router/ 或 src/routes/ 下的文件
  - react-router v5/v6：提取 `<Route>` 或 `useRoutes` 配置中的 path → component 映射
  - 按路由级别划分模块
- 组件目录：src/components/ 或 src/features/ 的一级子目录作为候选模块
- 页面目录：src/pages/ 或 src/views/ 的一级子目录作为候选模块

**扫描文件列表**：
- `src/router/**/*.{js,jsx,ts,tsx}` — 路由配置
- `src/App.{js,jsx,ts,tsx}` — 根路由定义
- `src/components/` — 组件目录结构
- `src/features/` — 功能模块目录（如存在）

#### Vue

**检测信号**：package.json 中 dependencies 包含 "vue"

**模块提取**：
- 路由配置：扫描 `src/router/index.{js,ts}`，提取 routes 数组中的 path → component 映射
- 组件目录：`src/components/` 的一级子目录
- 视图目录：`src/views/` 的一级子目录
- Vuex/Pinia store：`src/store/` 下的模块划分

**扫描文件列表**：
- `src/router/index.{js,ts}`
- `src/components/**/*.vue`
- `src/views/**/*.vue`
- `src/store/**/*.{js,ts}`

#### Next.js

**检测信号**：package.json 中 dependencies 包含 "next"

**模块提取**：
- Pages Router：`pages/` 目录下每个文件为一个路由模块
- App Router：`app/` 目录下每个包含 `page.{tsx,jsx,ts,js}` 的目录为一个路由模块
- API 路由：`pages/api/` 或 `app/api/` 下的路由

**扫描文件列表**：
- `next.config.{js,mjs,ts}`
- `pages/**/*.{js,jsx,ts,tsx}` 或 `app/**/page.{tsx,jsx,ts,js}`
- `src/pages/**/*.{js,jsx,ts,tsx}` 或 `src/app/**/page.{tsx,jsx,ts,js}`

#### Angular

**检测信号**：package.json 中 dependencies 包含 "@angular/core"

**模块提取**：
- NgModule：扫描 `*.module.ts`，提取 `@NgModule` 装饰器中的 declarations/imports/exports
- 路由：RouterModule 定义，提取 routes 配置
- 按 Angular 目录惯例划分（一个目录一个模块）

**扫描文件列表**：
- `angular.json`
- `src/app/**/*.module.ts`
- `src/app/**/routing.module.ts` 或 `src/app/**/-routing.module.ts`

### 后端 Python 框架

#### Django

**检测信号**：存在 `manage.py` 或 settings.py 中 INSTALLED_APPS 包含 Django 应用

**模块提取**：
- Django Apps：扫描每个 app 的 `apps.py`，提取 `name` 和 `label`
- INSTALLED_APPS：从 settings.py 提取已安装 app 列表（排除 `django.contrib.*`）
- 每个 app 目录即为一个模块

**扫描文件列表**：
- `manage.py`
- `*/settings.py` 或 `*/settings/*.py`
- `*/apps.py`
- `*/urls.py`（路由配置）
- `*/models.py`（数据模型）

#### Flask

**检测信号**：代码中存在 `from flask import` 或 `import flask`

**模块提取**：
- Blueprint：扫描 `Blueprint()` 调用，提取蓝图名称
- 蓝图注册：`app.register_blueprint()` 调用，提取蓝图挂载点（url_prefix）
- 每个蓝图即为一个模块

**扫描文件列表**：
- `{app_name}/__init__.py` — 应用工厂
- `{app_name}/views.py` 或 `{app_name}/routes.py` — 路由定义
- 各蓝图目录下的 `__init__.py` 或 `routes.py`
- `wsgi.py` 或 `app.py` — 入口文件

#### FastAPI

**检测信号**：代码中存在 `from fastapi import` 或 `import fastapi`

**模块提取**：
- APIRouter：扫描 `APIRouter()` 实例，提取 `prefix` 和 `tags`
- 路由注册：`app.include_router()` 调用，提取路由器挂载信息
- 每个 router 实例对应一个模块

**扫描文件列表**：
- `main.py` 或 `app.py` — 应用入口
- `*/router.py` 或 `*/routes.py` — 路由定义
- `*/api/**/*.py` — API 端点
- `*/schemas/*.py` — 数据校验 schema（Pydantic）

#### Tornado

**检测信号**：代码中存在 `import tornado` 或 `from tornado import`

**模块提取**：
- Application handlers：扫描 `tornado.web.Application()` 配置，提取 `(path, Handler)` 对
- RequestHandler 子类：每个 Handler 类为一个路由处理模块
- 按功能分组 handlers

**扫描文件列表**：
- `app.py` 或 `main.py` — 入口和 Application 配置
- `handlers/` 或 `views/` — handler 目录
- `*/urls.py` — URL 配置

### Monorepo 工具链

**检测信号**：
- pnpm：`pnpm-workspace.yaml`
- Lerna：`lerna.json`
- Turborepo：`turbo.json`
- Nx：`nx.json`

**处理方式**：
- 从配置文件提取 workspace 目录列表
- 每个 workspace 视为独立工程，各自执行分区判定和模块发现
- 最终合并生成一个统一的 MAP.md

---

## 依赖聚类分析（2b）

对 2a 声明式信号扫描**未覆盖**的文件执行依赖聚类。

### Python 依赖聚类

1. **构建依赖图**
   - 扫描未覆盖的 `.py` 文件
   - 从每个文件提取 `import X` 和 `from X import Y` 语句
   - 将文件内 import 解析为项目内相对路径（排除第三方库和标准库）
   - 节点 = 文件（或目录），边 = import 关系

2. **识别聚集簇**
   - 使用连通分量分析：将相互有 import 关系的文件归为一组
   - 如果一个连通分量过大，按目录边界进一步拆分

3. **粒度阈值**
   - **过小**（< 3 个文件）：合并到 import 关系最密切的相邻簇
   - **过大**（> 30 个文件）：按一级子目录拆分为多个候选模块
   - **正常**（3-30 个文件）：直接作为一个候选模块

4. **命名规则**
   - 使用簇中文件的最深公共父目录名作为模块名
   - 如公共父目录是 `src/` 或 `app/`，使用下一级目录名

### 前端依赖聚类

1. **构建依赖图**
   - 扫描未覆盖的 `.{js,jsx,ts,tsx,vue}` 文件
   - 从每个文件提取 `import ... from '...'` 语句
   - 仅保留项目内相对 import（排除 `node_modules` 和外部包）
   - 节点 = 文件，边 = import 关系

2. **识别聚集簇**
   - 同 Python 方法：连通分量分析
   - 过大的分量按组件/功能目录拆分

3. **粒度阈值**
   - 同 Python 阈值规则

4. **命名规则**
   - 使用组件/功能目录名
   - kebab-case 目录名保持原样或转换为 PascalCase

---

## 目录兜底策略（2c）

对 2b 依赖聚类**仍未覆盖**的文件执行目录兜底。

### 启用条件

- 2a 和 2b 合并后，仍有 > 10% 的源码文件未被分配到任何模块

### 过滤规则

排除以下非业务目录（不作为模块候选）：

**通用**：`.git/`, `.github/`, `dist/`, `build/`, `out/`, `tmp/`, `temp/`, `docs/`, `tests/`, `test/`, `__tests__/`, `scripts/`, `migrations/`, `seeds/`, `fixtures/`

**Python**：`__pycache__/`, `venv/`, `.venv/`, `env/`, `egg-info/`, `.tox/`, `.mypy_cache/`

**前端**：`node_modules/`, `.next/`, `.nuxt/`, `coverage/`, `public/assets/`, `static/`

**仅含配置文件**：目录中只有 `.{json,yaml,yml,toml,ini,cfg,conf}` 文件且无代码文件

### 模块命名

- 使用目录原始名称
- 如目录名为通用名（如 `src/`, `lib/`, `app/`），检查其一级子目录，每个子目录作为一个候选模块

### 标注

在模块清单的「发现方式」列标注为 `目录推断·待确认`。

在模块领域层文档头部添加标注：

```markdown
> **[自动推断·待确认]** 本模块边界由目录结构自动推断，未经人工确认。建议核实模块划分是否合理。
```
