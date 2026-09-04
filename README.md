# TaskGrid · 分布式任务调度与沙箱执行平台

用户提交 Python 代码 → 控制中心异步调度到工作节点 → 在 Docker 沙箱中**隔离执行** → 结果写入 Elasticsearch 供全文检索。完整实现了从 API 到异步任务、到沙箱执行、到日志检索的分布式系统闭环。

## 技术栈

| 层 | 技术 |
|---|---|
| Web | Django 6 + DRF 3 + SimpleJWT（RBAC） |
| 异步调度 | Celery + Redis（broker/result backend） |
| 沙箱执行 | Docker SDK（docker-out-of-docker） |
| 检索 | Elasticsearch（全文检索，降级设计） |
| 存储 | PostgreSQL |
| 部署 | Nginx + Gunicorn + docker-compose |

## 核心架构

```
POST /api/v1/tasks/
  → select_node() 按负载选节点，写入 worker_id
  → execute_task.delay() 入 Celery 队列
  → worker 消费，状态机 PENDING→RUNNING
  → SandboxExecutor 起一次性 Docker 容器隔离执行
  → 状态机 →SUCCESS/FAILED/TIMEOUT，写入 ES
```

关键设计：

- **状态机收口**：`Task.transit()` 是唯一改状态入口，非法转移抛 ValueError，杜绝状态乱飞
- **调度策略**：`select_node(strategy)` 策略模式，least_loaded 按 CPU/内存选节点；心跳超 60s 自动离线，故障任务可重新调度
- **四级优先级**：critical/high/default/low 四队列路由，紧急任务优先消费
- **运行中取消**：`cancel_requested_at` 标记 + executor 轮询检测 → 强杀 Docker 容器，异步生效
- **沙箱四层隔离**：非 root 用户 + 只读文件系统（仅 `/tmp` 可写）+ 禁用网络 + 资源限制（mem 256m / 1 CPU / 64 进程 / 超时 30s），OOM 检测（退出码 137）
- **降级设计**：ES 失败只记日志，绝不影响任务主流程——辅助系统不能拖垮关键路径
- **集群化部署**：web/worker/nginx/PG/Redis/ES 全容器化编排，worker 容器挂载宿主 docker.sock 起沙箱（Docker-out-of-Docker）。线上 2GB 内存去掉了 ES

线上演示：`http://123.207.204.108:8080`（腾讯云 2C2G VPS）

## 快速开始

### 开发模式（本机 + 依赖容器）

```bash
# 1. 启动依赖容器（PostgreSQL / Redis / ES）
scripts\start_dev.bat

# 2. 迁移 + 启动开发服务器
python manage.py migrate
python manage.py runserver

# 3. 另开窗口启动 Celery worker（Windows 用 -P solo）
scripts\start_celery.bat
```

### 生产模式（全容器化集群）

```bash
scripts\start_prod.bat
# 入口：http://localhost:8080（Nginx 反代 + gunicorn + celery worker）
```

## API 摘要

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/register/` | 注册 |
| POST | `/api/v1/auth/login/` | 登录（JWT） |
| CRUD | `/api/v1/tasks/` | 任务管理（owner 隔离） |
| POST | `/api/v1/tasks/{id}/status/` | 手动改状态（状态机校验） |
| POST | `/api/v1/tasks/{id}/cancel/` | 取消任务 |
| GET | `/api/v1/nodes/` | 节点列表（仅管理员） |
| GET | `/api/v1/logs/search/?q=` | 日志全文检索 |

接口文档：`/api/docs/`（Swagger）。

## 测试与代码规范

```bash
pytest                              # 85 个用例，覆盖率 90%
black . && isort . && flake8 .      # 代码规范检查
pre-commit run --all-files          # 提交前钩子
```

## 目录结构

```
apps/
  users/      认证 + RBAC 权限类
  tasks/      任务 CRUD + 状态机 + Celery 任务
  nodes/      节点注册/心跳/调度策略
  sandbox/    Docker 沙箱执行器
  logs/       ES 日志索引/检索
config/       settings（base/dev/prod/test 拆分）
docker/       沙箱镜像 + nginx 配置
docs/         8 个阶段的学习与验证文档
```

## 阶段学习文档

`docs/phase0_setup.md` ~ `docs/phase8_testing.md`，每个阶段含架构讲解、验证步骤、完成标准，记录了完整的学习与排坑过程。
