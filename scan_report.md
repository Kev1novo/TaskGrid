# TaskGrid 项目扫描报告

生成日期：2026-09-17 | 覆盖范围：安全、性能、代码质量、测试、基础设施、依赖

---

## 一、安全问题

### 1.1 [高] `select_for_update()` 未包裹事务，并发保护失效

**位置**：`apps/tasks/views.py` 的 `cancel()` 和 `update_status()` 方法

**问题**：两个方法使用 `Task.objects.select_for_update().get(pk=pk)` 防止并发竞态，但 Django 默认 `autocommit=True` 且未加 `@transaction.atomic` 装饰器。没有活跃事务时，PostgreSQL 上的 `SELECT ... FOR UPDATE` 在每个 SQL 语句自己的隐式事务中获取并立即释放行锁——后续的 `task.save()` 完全没有锁保护。

**影响**：两个并发请求同时取消同一个 RUNNING 任务，或用户取消的同时 worker 刚好结束任务，可能造成状态不一致。

**修复**：在方法上加 `@transaction.atomic`，或将 `select_for_update()` + 后续所有操作放入同一个 `with transaction.atomic():` 块。

---

### 1.2 [中] 生产 Docker Compose 中 SECRET_KEY 有可猜测的默认值

**位置**：`docker-compose.prod.yml` 第 6 行

**问题**：`SECRET_KEY: ${SECRET_KEY:-change-me-taskgrid-prod-key}`。如果运维人员未设置环境变量，系统会使用这个硬编码的 fallback。虽然后续 Django 启动时 prod.py 会检查 `os.environ.get("SECRET_KEY")` 是否存在（存在就不会抛错），但一个已知的 fallback 值是可被攻击者利用的。

**影响**：使用默认值部署时，JWT token 可被伪造，导致任意用户冒充。

**修复**：删除 fallback 值，或在 compose 启动时强制校验环境变量是否已设置。

---

### 1.3 [中] Flower 监控密码硬编码在脚本中

**位置**：`scripts/start_celery.bat` 第 3 行

**问题**：`--basic_auth=admin:taskgrid-flower`。密码以明文形式存储在版本仓库中，且所有能访问代码仓库的人都知道这个密码。

**影响**：生产环境如果暴露 Flower 端口，攻击者可登录监控面板查看 Celery 队列、任务状态、甚至触发任务。

**修复**：从环境变量读取密码，或使用独立的凭据管理系统。

---

### 1.4 [中] 生产环境 HTTPS 配置与线上实际部署矛盾

**位置**：`config/settings/prod.py`，`CLAUD.md`

**问题**：prod.py 默认 `SECURE_SSL_REDIRECT=True`，且 `SESSION_COOKIE_SECURE` 和 `CSRF_COOKIE_SECURE` 跟随该值。但 CLAUDE.md 明确写道"腾讯云部署适配：SECURE_SSL_REDIRECT=False（暂无 TLS）"——意味着线上实例在纯 HTTP 下运行。如果忘记设置环境变量，可能导致无限重定向循环，或 secure cookie 在 HTTP 下不被浏览器发送。

**修复**：在 docker-compose.prod.yml 中显式设置 `SECURE_SSL_REDIRECT=false`，或确保生产环境确实有 TLS。

---

### 1.5 [低] ES 在生产 Docker Compose 中无认证

**位置**：`docker-compose.prod.yml` 第 45 行

**问题**：`xpack.security.enabled=false`。虽然 ES 只在 compose 内部网络可达，但一旦容器被攻破，整个日志数据可被窃取。

**影响**：辅助系统，风险有限。但考虑到 ES 8.x 默认开启安全特性，应保持开启。

---

## 二、性能问题

### 2.1 [低] 每次沙箱执行都检查镜像存在

**位置**：`apps/sandbox/executor.py` 第 78-85 行

**问题**：`ensure_image()` 在每个 `execute()` 调用时都执行 `client.images.get(image)` 查询 Docker 守护进程的本地镜像列表。镜像在部署后几乎不会变，每次查询是多余的。

**修复**：缓存镜像存在状态（例如模块级 `set` 或 `lru_cache`），或在 `SandboxExector.__init__()` 中一次性检查。

---

### 2.2 [低] search_logs 硬编码返回条数上限

**位置**：`apps/logs/services.py` 第 87 行

**问题**：`search_logs` 的 `size` 参数默认值为 50，且 LogSearchView 未提供客户端控制该参数的能力。大结果集无法分页。

**影响**：调用方无法获取超过 50 条的结果。

**修复**：从 query_params 透传 `size` 参数（设合理上限如 500）。

---

### 2.3 [低] ES 客户端未配置连接池

**位置**：`apps/logs/services.py` 第 49 行

**问题**：`Elasticsearch(settings.ELASTICSEARCH_URL)` 使用默认连接池参数（`maxsize=10`）。对于高并发写入场景，可能成为瓶颈。

**影响**：目前 ES 是辅助系统，写入失败降级记日志，影响有限。

**修复**：按需配置 `maxsize` 参数。

---

## 三、代码质量问题

### 3.1 [高] `select_for_update()` 未包裹事务——同 1.1

同上，并发保护实际上不生效。这是安全+代码质量双料问题。

---

### 3.2 [中] cancel() 中 RUNNING 分支注释与实际行为不一致

**位置**：`apps/tasks/views.py` 第 158-164 行

**问题**：注释写"已经请求过取消了，直接返回当前状态（幂等）"，但代码没有做幂等判断——每次请求都执行 `cancel_requested_at = timezone.now()` 并保存。每次请求都会更新时间戳，不是真正的幂等。

**修复**：添加 `if task.cancel_requested_at: return Response(...)` 提前返回。

---

### 3.3 [中] `_dispatch_task` 未处理 select_node() 异常

**位置**：`apps/tasks/views.py` 第 27-43 行

**问题**：`select_node()` 内部调用 `mark_offline_if_stale()`，后者执行数据库查询。如果 DB 连接故障，异常会冒泡到 `create()` 和 `retry()` 视图，返回 500 错误。同时，如果没有任何在线节点，`select_node()` 返回 `None`，此时 `task.worker_id` 被设为 `""`（空字符串）。任务虽然创建了但没有可用的 worker，会被卡在 PENDING 状态永远不会被执行。

**修复**：增加降级/通知逻辑（如设置 `error_message`），或直接拒绝创建。

---

### 3.4 [中] reschedule_tasks 绕过状态机

**位置**：`apps/nodes/management/commands/reschedule_tasks.py` 第 32-34 行

**问题**：直接 `task.status = Task.Status.PENDING` 跳过了 `transit()` 方法的状态机约束。虽然管理命令有其合理性（`transit()` 不允许 RUNNING→PENDING，但重新调度恰好需要这个转移），但缺少注释说明设计理由。

**修复**：添加注释说明为什么必须绕过状态机。

---

### 3.5 [低] nodes/admin.py 没有注册模型

**位置**：`apps/nodes/admin.py`

**问题**：文件只包含了 `# Register your models here.` 注释，未注册 `Node` 模型到 Django admin。

**影响**：管理员无法通过 Django 后台查看/管理节点。

**修复**：注册 Node 模型到 admin。

---

### 3.6 [低] ES _client 单例在开发热重载时可能泄漏

**位置**：`apps/logs/services.py` 第 42-49 行

**问题**：`_es_client` 是模块级全局变量，Django 开发模式的 `runserver` 热重载会重新加载模块，但旧连接不会被显式关闭。

**影响**：极小。

---

### 3.7 [低] TaskSerializer 暴露了 `cancel_requested_at` 字段

**位置**：`apps/tasks/serializers.py` 第 24 行

**问题**：`cancel_requested_at` 属于内部实现细节（用于 worker 轮询检测的标记），对普通用户暴露此字段可能引起困惑。

---

## 四、测试覆盖缺口

### 4.1 [中] select_node() 返回 None 的场景未测试

**覆盖**：`apps/tasks/tests/test_api.py`

**缺口**：当没有在线节点时，`select_node()` 返回 `None`。创建任务时 `worker_id` 会被设为空字符串，任务永远卡在 PENDING。此路径没有测试覆盖。

### 4.2 [中] 无并发竞态测试

**覆盖**：全部 test 文件

**缺口**：`select_for_update()` 设计用于防并发，但没有针对两个请求同时修改同一个任务的测试（如 cancel + worker 同时结束任务，或两个 cancel 同时请求）。

### 4.3 [中] 无限流测试

**覆盖**：`apps/users/tests/`

**缺口**：base.py 配置了 AnonRateThrottle（100/hour）和 UserRateThrottle（1000/hour），但没有测试验证限流是否生效。

### 4.4 [低] admin 替他人重试无测试

**覆盖**：`apps/tasks/tests/test_api.py`

**缺口**：`retry()` 使用 `self.get_object()` 权限检查，管理员应能为他人重试。没有测试覆盖此场景。

### 4.5 [低] container.logs() 读取失败无测试

**覆盖**：`apps/sandbox/tests/test_executor.py`

**缺口**：`_get_logs()` 捕获 `docker.errors.APIError` 并返回空字符串，但没有测试验证此降级路径。

---

## 五、基础设施问题

### 5.1 [低] CI 缺少安全扫描

**位置**：`.github/workflows/ci.yml`

**缺口**：pipeline 只有 black/isort/flake8 + pytest。没有集成：
- `bandit`（Python 静态安全分析）
- `safety` 或 `pip-audit`（依赖漏洞检查）

**建议**：添加 `pip install bandit safety && bandit -r apps/ && safety check` 到 CI 步骤。

### 5.2 [低] 缺少业务指标和监控

**缺口**：虽然安装了 `prometheus_client`（Flower 的传递依赖），但 Django 应用本身没有暴露 Prometheus metrics。没有业务指标：任务执行延迟、队列深度、节点数、失败率。

**建议**：选择 `django-prometheus`，或在现有的 `/health/` 端点添加业务指标。

---

## 六、依赖问题

### 6.1 [低] humanize 未在项目代码中使用

**详情**：`humanize==4.16.0` 被锁为依赖，但全项目无一处 `import`。可考虑移除。

### 6.2 [低] prometheus_client 为 Flower 传递依赖

**详情**：项目代码中无 `prometheus_client` 引用。如果未来计划自行暴露 metrics 可以保留。

### 6.3 [低] pywin32 已通过 requirements-prod.txt 分离

**详情**：`requirements.txt` 含 `pywin32`（Windows 专用），`requirements-prod.txt`（不含）用于容器。CI 用 `grep -v` 跳过。当前设计合理。

### 6.4 [低] 多个传递依赖未直接使用

**列表**：`jsonschema`、`jsonschema-specifications`、`referencing`、`rpds-py`、`six`、`pytz`、`tzdata`

**说明**：这些都属于 drf-spectacular 或 elasticsearch SDK 的传递依赖，无需处理。

---

## 七、其他观察

### 7.1 [信息] 代码注释质量优秀

全项目中英文文档和注释质量非常高，几乎每个函数、每个设计决策都有清晰的注释说明 **why**（而非 what）。

### 7.2 [信息] 测试覆盖率高且测试质量好

85 个测试用例覆盖了状态机、API 权限、Celery 任务、节点心跳、ES 日志、管理命令等主要路径，使用合理的 mock 策略（fake_sandbox、fake_es）。

### 7.3 [信息] 降级设计做得很好

ES 写入读取失败只记日志不影响主流程、celery 异常处理多处 try/catch 兜底、Docker API 错误以 `SandboxResult.error` 返回而非抛异常——这些设计模式应保持。

---

## 优先级建议汇总

| 序号 | 类别 | 标题 | 优先级 | 预估工作量 |
|------|------|------|--------|-----------|
| 1.1/3.1 | 安全/代码质量 | `select_for_update()` 无事务包裹 | **高** | 小（加3行注解） |
| 1.2 | 安全 | SECRET_KEY 可猜测 fallback | **中** | 小（删默认值） |
| 1.3 | 安全 | Flower 密码硬编码 | **中** | 小（改读环境变量） |
| 1.4 | 安全 | HTTPS 配置与线上矛盾 | **中** | 小（加 .env 配置） |
| 3.2 | 代码质量 | cancel() 幂等注释与实际不符 | **中** | 极小（加提前返回） |
| 3.3 | 代码质量 | select_node 返回 None 无处理 | **中** | 小（加降级逻辑） |
| 3.4 | 代码质量 | reschedule_tasks 绕过状态机 | **中** | 极小（加注释） |
| 4.1 | 测试 | 无 select_node=None 测试 | **中** | 小（写2个用例） |
| 4.2 | 测试 | 无并发竞态测试 | **中** | 中（写并发测试） |
| 4.3 | 测试 | 无限流测试 | **中** | 小（写限流测试） |
| 2.1 | 性能 | 每次执行检查镜像存在 | 低 | 小（加缓存） |
| 2.2 | 性能 | search_logs size 硬编码 50 | 低 | 极小（透传参数） |
| 3.5 | 代码质量 | nodes 未注册 admin | 低 | 极小（加几行） |
| 3.7 | 代码质量 | 暴露内部字段 cancel_requested_at | 低 | 极小（exclude 字段） |
| 4.4 | 测试 | admin 替他人重试无测试 | 低 | 小（写用例） |
| 4.5 | 测试 | logs 读取失败无测试 | 低 | 小（写用例） |
| 5.1 | 基础设施 | CI 无安全扫描 | 低 | 小（加2行 CI） |
| 5.2 | 基础设施 | 缺少业务 metrics | 低 | 大（引入监控栈） |
| 6.1 | 依赖 | humanize 未使用 | 低 | 极小（删一行） |