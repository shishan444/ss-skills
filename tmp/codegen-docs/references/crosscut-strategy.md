---
查阅条件：Step 6 识别横切关注点时查阅。
---

# 横切关注点识别策略

## 识别方法

三重信号扫描，任一信号匹配即识别为该关注点存在：

1. **依赖扫描**：从 requirements.txt / pyproject.toml / package.json 中检测相关依赖
2. **Import 扫描**：从代码中检测相关 import 语句
3. **文件/目录扫描**：从目录结构和文件名中检测相关信号

## 信号词典

### 认证鉴权

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `PyJWT`, `python-jose`, `authlib`, `oauthlib`, `passlib` |
| Python import | `from flask_login`, `from fastapi.security`, `from django.contrib.auth`, `import jwt` |
| 前端依赖 | `jwt-decode`, `auth0-js`, `next-auth`, `vuex-persistedstate` |
| 前端 import | `from 'next-auth'`, `useAuth`, `useUser` |
| 目录/文件 | `auth/`, `middleware/auth*`, `guards/`, `interceptors/auth*` |

### 错误处理

| 信号来源 | 匹配模式 |
|----------|----------|
| Python import | `from fastapi.exception_handlers`, `from django.core.exceptions` |
| Python 装饰器 | `@app.errorhandler`, `@exception_handler` |
| 前端依赖 | `react-error-boundary`, `sentry` |
| 前端组件 | `ErrorBoundary`, `ErrorFallback`, `error.tsx`, `Error.vue` |
| 目录/文件 | `exceptions/`, `errors/`, `handlers/error*` |

### 数据库 / 存储

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `SQLAlchemy`, `django`, `mongoengine`, `redis`, `alembic`, `peewee` |
| Python import | `from sqlalchemy`, `from django.db`, `from mongoengine`, `import redis` |
| 前端依赖 | `@prisma/client`, `dexie`, `localforage` |
| 目录/文件 | `models/`, `db/`, `database/`, `repository/`, `migrations/`, `schemas/` |

### 日志 / 监控

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `structlog`, `loguru`, `sentry-sdk`, `prometheus-client` |
| Python import | `import logging`, `import structlog`, `from sentry_sdk` |
| 前端依赖 | `@sentry/react`, `datadog`, `logrocket` |
| 目录/文件 | `logging/`, `monitoring/`, `metrics/`, `logger.*` |

### 配置管理

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `python-dotenv`, `pydantic`, `dynaconf` |
| Python import | `from pydantic_settings`, `from dynaconf`, `from dotenv` |
| 前端依赖 | `dotenv`, `config` |
| 文件 | `.env`, `.env.*`, `config.*`, `settings.*` |

### 缓存

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `redis`, `memcache`, `cachetools` |
| Python import | `from functools import lru_cache`, `from cachetools` |
| 前端依赖 | `react-query`, `swr`, `@tanstack/query` |
| 前端 import | `useQuery`, `useSWR`, `useCache` |
| 目录/文件 | `cache/`, `redis/` |

### 序列化 / 校验

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `pydantic`, `marshmallow`, `cerberus` |
| Python import | `from pydantic`, `from marshmallow` |
| 前端依赖 | `zod`, `joi`, `yup` |
| 前端 import | `from 'zod'`, `from 'yup'` |

### CORS / 安全

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 中间件 | `CORSMiddleware`, `CORS`, `@app.middleware` |
| 前端依赖 | `helmet` |
| 文件 | `security/`, `cors.*` |

### 任务队列 / 异步

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `celery`, `rq`, `huey`, `dramatiq` |
| Python import | `from celery`, `import rq`, `from huey` |
| 目录/文件 | `tasks/`, `workers/`, `jobs/`, `queue/` |

### API 文档

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `fastapi`（内置 Swagger）, `flask-restx`, `flasgger` |
| 前端依赖 | `swagger-ui`, `redoc` |
| 文件 | `swagger.*`, `openapi.*` |

### 测试

| 信号来源 | 匹配模式 |
|----------|----------|
| Python 依赖 | `pytest`, `unittest`, `mock`, `factory-boy` |
| 前端依赖 | `jest`, `vitest`, `cypress`, `playwright`, `testing-library` |
| 目录/文件 | `tests/`, `__tests__/`, `*.test.*`, `*.spec.*` |

---

## 识别后处理

1. **去重**：同一关注点被多个信号匹配时只生成一个文档
2. **合并**：强关联的关注点可合并为一个文档（如认证鉴权 + CORS/安全 → 安全体系）
3. **过滤**：测试关注点默认不生成横切文档（除非工程有特殊测试策略需记录）
4. **优先级**：当关注点过多时，按以下优先级生成：

| 优先级 | 关注点 | 说明 |
|--------|--------|------|
| P1 | 认证鉴权、数据库/存储、错误处理 | 系统核心基础设施 |
| P2 | 日志/监控、配置管理、缓存 | 运维可观测性相关 |
| P3 | 序列化/校验、CORS/安全、任务队列、API 文档 | 辅助性关注点 |
