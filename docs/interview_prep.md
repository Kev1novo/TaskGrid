# 面试准备：TaskGrid 项目话术

## 简历项目描述（3-5 行）

> **TaskGrid：分布式任务调度与沙箱执行平台**
> 用户提交 Python 代码，控制中心异步调度到工作节点，在 Docker 沙箱中隔离执行，结果写入 Elasticsearch 供全文检索。基于 Django + DRF 实现 JWT 认证与 RBAC、任务状态机；Celery + Redis 异步调度；Docker SDK 实现四层隔离沙箱；节点心跳 + 故障转移 + 负载调度策略；Nginx + Gunicorn + docker-compose 全容器化部署；pytest 77 个用例覆盖率 91%。

## 项目亮点（主动讲这几点）

1. **完整闭环**：不是 CRUD 演示，是一条完整的分布式链路——API 提交 → 异步调度 → 沙箱隔离执行 → 日志检索
2. **状态机收口**：`Task.transit()` 是唯一状态变更入口，非法转移抛异常，从设计上杜绝脏状态
3. **沙箱安全**：四层隔离（非 root + 只读 FS + 禁网 + 资源限制），把用户代码当不可信输入对待
4. **降级设计**：ES 失败只记日志不影响任务主流程——体现了"辅助系统不能拖垮关键路径"的工程思想
5. **故障转移闭环**：心跳超时自动离线 → 任务重新调度，节点故障可自愈

## 常考问题 Q&A

### Q1：为什么用 Celery 而不用多线程/多进程？
**答**：Celery 是分布式任务队列，核心价值是**解耦和横向扩展**。任务通过 Redis 入队，worker 可以多节点部署、按负载横向扩容，进程崩溃任务可重试。多线程受 GIL 限制、内存共享，多进程要自己管进程池和通信，都不适合"HTTP 请求快速返回 + 后台异步执行"的场景。Celery 还自带重试、超时、监控（Flower）、结果存储。

### Q2：状态机为什么单独用 transit() 收口？
**答**：任务状态是核心业务不变量。如果不收口，任何代码都能直接改 `task.status`，状态会乱（比如 SUCCESS 又变回 RUNNING）。`transit()` 用一张"允许转移表"收口，非法转移抛 ValueError。这样**所有状态变更走同一道校验**，行为可预测、可测试——测试里就把全路径覆盖了。

### Q3：沙箱怎么做到隔离？为什么用 Docker 而不是子进程？
**答**：四层隔离：① 非 root 用户（容器内 sandbox 用户，不能提权）；② 只读文件系统（仅 /tmp 可写，代码改不了宿主文件）；③ 禁用网络（`network_disabled`，防外传数据）；④ 资源限制（内存 256m、1 CPU、64 进程、30s 超时，超时强杀）。Docker 相比子进程：cgroup 资源限制成熟、文件系统/网络隔离内核级、进程逃逸面小、一次性容器用完即删。

### Q4：ES 为什么不做业务主存储？
**答**：ES 擅长全文检索（倒排索引），但事务、关联、强一致性弱。业务数据在 PostgreSQL（强一致、事务），日志/检索数据进 ES。且 ES 是辅助系统——**它挂掉任务照跑**（降级设计：写入失败只记日志），这是微服务里"辅助系统不能拖垮关键路径"的思想。

### Q5：节点故障转移怎么实现的？
**答**：每个 worker 进程内起后台线程，每 30s 上报心跳（带 CPU/内存负载）到数据库。`mark_offline_if_stale` 把超过 60s 未心跳的在线节点标记离线；调度前先做一次故障检测，只选在线节点；离线节点的任务可用管理命令重新调度到在线节点。

### Q6：调度策略为什么用策略模式？
**答**：`select_node(strategy)` 把"选哪个节点"抽象成策略，least_loaded（按负载）是默认，round_robin 是备选。新增策略只需加一个分支，不动调用方。这是可扩展性的体现。

### Q7：docker.sock 挂载有安全风险吗？
**答**：有。worker 容器挂载宿主 `/var/run/docker.sock` 后，等于能控制宿主 Docker daemon（所以 worker 必须 root，但这只影响 worker 本身）。**风险边界**：沙箱容器内仍是 sandbox 用户 + 只读 + 禁网，用户代码在沙箱里无法访问 socket；但如果沙箱被攻破逃逸到 worker 容器，就有隐患。生产上更严格的方案是每任务起独立 daemon，或限制 API 权限。这个取舍面试时要能说出来——说明你懂安全边界。

### Q8：怎么保证用户之间数据隔离？
**答**：三层：① JWT 认证（SimpleJWT，access 30min/refresh 7d）；② RBAC 权限类——`IsOwnerOrAdmin` 对象级权限，普通用户只能访问 owner 是自己的资源；③ 查询层兜底——`get_queryset` 直接按 owner 过滤，越权访问返回 404（不泄露资源存在性），连 ES 日志检索也按 owner 过滤。前端隐藏按钮不算安全，后端查询过滤才算。

### Q9：项目怎么部署的？
**答**：全容器化。`docker-compose.prod.yml` 编排 web（Gunicorn 3 workers×2 threads）+ worker（Celery）+ Nginx + PG/Redis/ES。启动顺序用 `depends_on: condition: service_healthy` 控制：web 等基础设施健康 → 跑 migrate + collectstatic → 起 Gunicorn；worker 等 web 健康再消费任务。Nginx 反代到 Gunicorn，直接服务静态文件。生产 settings 强制 SECRET_KEY 必须由环境变量提供。

### Q10：遇到过什么印象深的 bug？
**答**：① 沙箱超时：Windows 命名管道上 `container.wait(timeout)` 抛 `ConnectionError` 而 TCP 抛 `ReadTimeout`，两种都要捕获否则超时被误判为普通异常；② ES 客户端版本：服务器 8.x 配客户端 9.x 报 `Accept version must be 8 or 7`，锁版本解决；③ 测试阶段发现 `ensure_image()` 在 try 外导致镜像拉取失败时抛异常而非返回错误结果（死代码），测试暴露后修复。讲具体的 bug + 排查过程最有说服力。

## 简历技能标签建议

- Python / Django / DRF / Celery / Redis / PostgreSQL / Elasticsearch
- Docker / Docker SDK / Nginx / Gunicorn / docker-compose
- RESTful API / JWT / RBAC / 异步任务 / 分布式调度 / 状态机
- pytest / Git / Linux
