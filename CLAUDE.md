# CLAUDE.md

## 思考语言

**所有内部推理、思考过程必须使用中文。**

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

TaskGrid：分布式任务调度与沙箱执行平台（学习项目）。用户提交 Python 代码，控制中心异步调度到工作节点，在 Docker 沙箱中隔离执行，结果写入 Elasticsearch 供全文检索。

技术栈：Django 6 + DRF + SimpleJWT / Celery + Redis / Docker SDK（沙箱）/ Elasticsearch / PostgreSQL / Nginx + Gunicorn。

## 常用命令

所有命令在项目根目录、激活虚拟环境后执行（Windows，用 `.venv\Scripts\...`）：

```bash
# 激活虚拟环境（Git Bash）
source .venv/Scripts/activate

# 开发服务器
python manage.py runserver

# Celery worker + Flower 监控（弹两个新窗口，代码改了必须重启 worker）
scripts\start_celery.bat

# 开发依赖一键起（postgres/redis/ES）+ Django dev server + Celery worker
scripts\start_dev.bat

# 数据库迁移
python manage.py makemigrations
python manage.py migrate

# 节点故障检测 / 任务重新调度（管理命令）
python manage.py nodes_check
python manage.py reschedule_tasks

# 沙箱镜像构建（Dockerfile 改过后才需要）
scripts\build_sandbox.bat

# 生产集群一键起（web/worker/nginx/PG/Redis/ES 全容器化，首次构建慢）
scripts\start_prod.bat
# 只重新构建生产应用镜像
scripts\build_prod.bat

# 测试（需 dev postgres 容器在跑）
pytest
# 代码规范检查 / 格式化
black . && isort . && flake8 .
# 提交前钩子
pre-commit run --all-files
```

开发依赖容器（PostgreSQL/Redis/ES）：
```bash
docker compose -f docker-compose.dev.yml up -d
```

生产集群（`docker compose -f docker-compose.prod.yml up -d`），入口是 Nginx `http://localhost:8080`。注意 prod 与 dev 集群用不同的 compose 项目名（`taskgrid-prod` vs 默认），卷和端口完全隔离，互不影响。

## 架构

### 核心异步链路（理解全项目关键）

```
POST /api/v1/tasks/  (TaskViewSet.create)
  → select_node() 选择在线节点，写入 task.worker_id
  → execute_task.apply_async(args=[task.id], queue=priority_queue) 按优先级路由入队
  → Celery worker 消费，状态机 PENDING→RUNNING（soft_time_limit=33s / time_limit=38s）
  → SandboxExecutor 起一次性 Docker 容器隔离执行
  → 状态机 →SUCCESS/FAILED/TIMEOUT，写入 ES
```

### App 职责

- **apps/users** — 自定义 User（role 字段）、JWT 认证、RBAC 权限类（`IsAdmin` / `IsAdminOrSelf` / `IsOwnerOrAdmin`）。注意 `IsOwnerOrAdmin.has_permission` 必须返回登录校验，否则匿名用户会打到 500。
- **apps/tasks** — 核心业务。`Task.transit()` 是状态机（PENDING→RUNNING→SUCCESS/FAILED/TIMEOUT，PENDING→CANCELLED），非法转移抛 ValueError。`cancel_requested_at` 字段实现异步取消：用户请求取消 RUNNING 任务时打标记，executor 轮询检测后强杀容器。`TaskViewSet.create` 被重写以返回完整序列化对象（默认返回的是创建 serializer 的 data，没有 id）。`POST /tasks/{id}/retry/` 克隆终态任务（新 id，复用 name/code/params/priority）。优先级按 `_QUEUE_MAP` 路由到四个 Celery 队列。
- **apps/nodes** — 节点注册/心跳/故障检测。心跳由每个 worker 进程内的后台线程上报（`celery_events.py`），**不用 Celery beat**——beat 派发的任务会被任意 worker 消费，无法代表本节点负载。`select_node(strategy)` 是调度策略（策略模式）。
- **apps/sandbox** — `SandboxExecutor.execute()`：一次性容器、只读文件系统、网络禁用、内存/CPU/进程数限制、超时强杀、OOM 检测（退出码 137）。结果以 `SandboxResult` dataclass 返回，由 tasks 层翻译成任务状态。
- **apps/logs** — ES 索引/检索。**降级设计**：ES 失败只记日志，绝不影响任务主流程（辅助系统不能拖垮关键路径）。

### 配置

- `config/settings/` 按环境拆分：`base.py`（通用）+ `dev.py` / `prod.py`。`config/celery.py` 是 Celery 应用。
- `config/celery.py` 定义了 4 个优先级队列（`critical` / `high` / `default` / `low`），worker 按队列名消费对应级别的任务。`CELERY_TASK_DEFAULT_QUEUE = "default"`（base.py）确保未指定队列的任务落入默认队列。
- `apps/tasks/tasks.py` 的 `execute_task` 设置了 `soft_time_limit=33, time_limit=38`（沙箱默认 30s，给 3s 宽限触发软超时，再 5s 硬杀）。
- 配置项从 `.env` 读取（django-environ），模板见 `.env.example`。改配置后 `.env` 可能不生效需同步。
- `prod.py` 强制 `SECRET_KEY` 必须由环境变量提供（base 注册了 dev fallback，`env()` 永不抛错）。生产集群的环境变量由 `docker-compose.prod.yml` 的 `x-app-env` 锚点注入。
- `config/urls.py` 根路径 `/` 返回 SPA 单页应用（`TemplateView` → `templates/index.html`），`GET /health/` 检查 DB/Redis/Docker 连通性。

### 生产部署（阶段 7）

- 应用镜像 [Dockerfile](Dockerfile) web/worker 共用，非 root `app` 用户跑 gunicorn（3 workers × 2 threads）。依赖用 `requirements-prod.txt`（requirements.txt 剔除 pywin32 + 追加 gunicorn）。
- [docker-compose.prod.yml](docker-compose.prod.yml)：六服务编排，`depends_on: condition: service_healthy` 控制启动顺序（web 等 infra 健康后跑 migrate+collectstatic；worker 等 web 健康再消费任务）。
- **Docker-out-of-Docker**：worker 容器挂载宿主 `/var/run/docker.sock` 来起沙箱容器，所以 worker 的 `user: "0"`（socket 权限 root:docker）；沙箱容器内仍以 `sandbox` 用户隔离运行用户代码。
- Nginx [docker/nginx/nginx.conf](docker/nginx/nginx.conf) 反代 `web:8000` + 直接服务 `static_volume` 里的静态文件。

## 关键坑（Windows 特定）

- **Celery 用 `-P solo`**：Windows 上默认 prefork 池不稳定。脚本里已固定。
- **Docker SDK `container.wait(timeout=)` 超时**：Windows 命名管道抛 `requests.exceptions.ConnectionError`，TCP 抛 `ReadTimeout`。executor.py 两种都捕获，否则超时会被误判为普通异常。
- **`.bat` 脚本必须纯 ASCII**：cmd 用 GBK 解析 UTF-8 中文会崩。
- **Docker CLI 可能不在 PATH**：Docker Desktop 装在 `C:\Users\EDY\AppData\Local\Programs\DockerDesktop\resources\bin\`，必要时用完整路径或重启终端。
- **PowerShell 的 `curl` 是 `Invoke-WebRequest` 别名**：`-I` 等参数会报错，用 `curl.exe`；JSON body 用单引号不用 `\"`。
- **`python:3.12-slim` 没有 `ps` 命令**：验证 gunicorn 进程用 `docker compose logs web | grep "booting worker"`。
- **compose 项目名隔离**：prod 用 `name: taskgrid-prod`，否则卷名会与 dev 的 `test1_*` 冲突。`depends_on: condition: service_healthy` 只被 Compose v2 支持。

## 前端

- 单文件 SPA：[templates/index.html](templates/index.html)，Django `TemplateView` 直接服务，无外部 JS 依赖。
- **页面**：`#login` / `#register` / `#tasks`（列表+分页+筛选）/ `#tasks/create` / `#tasks/{id}`（详情+取消+重试）。
- **认证**：JWT token 存 localStorage，`api()` 函数拦截 401 自动用 refresh token 换新 access。过期跳登录页。
- **主题**：CSS 变量 + `prefers-color-scheme` 自动适配暗色/亮色模式。
- **注意**：后端 `PAGE_SIZE=20`，前端分页计算用 `/20`（之前硬编码 15 导致翻页 404，已修复）。

## 安全模型

- JWT 认证：`access` 30 分钟 / `refresh` 7 天。
- 沙箱四层隔离：非 root 用户 + 只读文件系统（仅 `/tmp` 可写）+ 禁用网络 + 资源限制（mem 256m / 1 CPU / 64 进程 / 超时 30s）。沙箱代码本质是用户提交的任意代码，按不可信输入对待。
- 节点管理 API 仅管理员；普通用户任务数据按 owner 过滤（包括 ES 日志检索）。

## 测试与规范

- **pytest**：85 个用例，覆盖率 91%。配置在 [pyproject.toml](pyproject.toml)（`config.settings.test`，Celery eager 模式），公共 fixtures 在 [conftest.py](conftest.py)（fake_sandbox / fake_es / auth_client）。测试库需 dev postgres 容器在跑。
- **mock 边界**：Docker（沙箱）、ES（日志）、psutil（心跳）、Celery `apply_async`（API 测试阻断真实派发）都打补丁，测试不碰真实 I/O。
- **规范**：black/isort（line-length 100）+ flake8（.flake8 排除 .venv/.git/migrations）。pre-commit 装 3 个钩子，git commit 时自动跑。
- 手动验证流程见 `docs/phase*_*.md` 各阶段文档。验证接口建议加 `-H "Accept: application/json"` 否则 DRF 返回可浏览 HTML。
