# 阶段 7：集群化部署（Nginx + Gunicorn + docker-compose）

## 已完成内容

### 1. 应用镜像 [Dockerfile](../Dockerfile)
- web（gunicorn）与 worker（celery）**共用同一镜像**，compose 用 `command` 覆盖启动命令
- 非 root：`app` 用户跑 gunicorn；worker 因要访问宿主 docker.sock 在 compose 里覆盖为 root
- 依赖清单用 [requirements-prod.txt](../requirements-prod.txt)：从 requirements.txt 剔除 `pywin32`（Windows 专用，Linux 装不上）+ 追加 `gunicorn`。保持同步命令：`grep -v '^pywin32==' requirements.txt > requirements-prod.txt`

### 2. 生产编排 [docker-compose.prod.yml](../docker-compose.prod.yml)
六服务一键起：**web / worker / nginx / postgres / redis / elasticsearch**
- `name: taskgrid-prod` — compose 项目名，卷名自动前缀 `taskgrid-prod_*`，与 dev 的 `test1_*` 卷**彻底隔离**
- 启动顺序靠 `depends_on: condition: service_healthy` + healthcheck：web 等 PG/Redis/ES 健康 → 跑 migrate + collectstatic → 起 gunicorn；worker 等 web 健康（表已建）才消费任务
- infra 三服务**不发布宿主端口**，与 dev 集群（5432/6379/9200）不冲突
- 应用环境变量（DJANGO_SETTINGS_MODULE/SECRET_KEY/DATABASE_URL 等）用 YAML 锚点 `x-app-env` 复用
- 静态文件：web collectstatic 写入 `static_volume` 命名卷，nginx 只读挂载同卷直接服务

### 3. Nginx 反向代理 [docker/nginx/nginx.conf](../docker/nginx/nginx.conf)
- `location /static/` → `alias` 直接服务 Django 静态文件（admin/DRF 浏览 API/Swagger）
- `location /` → `proxy_pass` 到 `web:8000`（gunicorn）
- gzip 压缩 JSON/HTML、`client_max_body_size 10m`（用户提交代码）、`proxy_read_timeout 120s`

### 4. settings 生产化
- [base.py](../config/settings/base.py)：`STATIC_URL = '/static/'`（相对路径在嵌套页面会生成 `/api/v1/static/...`）、新增 `STATIC_ROOT`、`STATICFILES_DIRS`
- [prod.py](../config/settings/prod.py)：`SECRET_KEY` 强制生产必须显式提供（base 给 dev 注册了 fallback，`env()` 永不抛错，须直接查 `os.environ`）

### 5. 启动脚本
- [scripts/start_prod.bat](../scripts/start_prod.bat) / .sh — 先构建沙箱镜像，再 `up -d --build`
- [scripts/build_prod.bat](../scripts/build_prod.bat) / .sh — 只构建应用镜像

## 学习与验证

### 重点学习点
1. **Gunicorn 多进程 vs runserver**：dev server 单进程、带 reload、为开发设计；gunicorn 是生产 WSGI 服务器，`--workers 3 --threads 2` 起多进程处理并发。worker 数经验公式 `(2×核数)+1`，但虚拟化环境（Docker Desktop 默认 2 vCPU）要下调。`--access-logfile -` 让访问日志进 stdout，`docker compose logs web` 可见
2. **Nginx 反向代理**：外部请求先进 nginx（80），按 `location` 分发——静态文件 nginx 直接返回（快），动态请求转发给 gunicorn。`alias` vs `root`：`alias /app/staticfiles/` 是把 `/static/foo` 映射到 `/app/staticfiles/foo`，`root` 会拼出 `/static/static/foo`
3. **docker-compose 编排**：`depends_on` 默认只保证"先启动"，`condition: service_healthy` 才保证"健康后再启动"；healthcheck 在容器内探测自己；命名卷首次挂载会把镜像内目录属主拷贝进卷——所以镜像里要 `chown app:app /app/staticfiles`
4. **Docker-out-of-Docker（DooD）**：worker 在容器里要再起沙箱容器，做法是挂载宿主 `/var/run/docker.sock`，docker-py `from_env()` 自动读 socket。**权限边界**：socket 属主 root:docker（660），worker 必须 root 才能打开——所以 worker 容器 `user: "0"`；但沙箱容器内仍以 `sandbox` 用户隔离运行用户代码，两层互不矛盾
5. **配置注入**：`setdefault('config.settings.dev')` 语义是"环境变量没设才用默认"，容器设 `DJANGO_SETTINGS_MODULE=config.settings.prod` 即可覆盖，代码不用改

### 验证步骤

前置：Docker Desktop 运行中。

1. （可选）停 dev 集群避免干扰：`docker compose -f docker-compose.dev.yml down`
2. **一键启动**（首次拉镜像 + 装依赖较久）：
```bash
scripts\start_prod.bat
```
3. 等 6 个服务都 healthy：
```bash
docker compose -f docker-compose.prod.yml ps
```
4. **【最大风险点】DooD 预检**——worker 里的 docker SDK 能否操作宿主 daemon：
```bash
docker compose -f docker-compose.prod.yml exec worker python -c "import docker; c=docker.from_env(); print('ping:', c.ping()); print([i.tags for i in c.images.list() if i.tags][:3])"
```
应输出 `ping: True` 且镜像列表含 `taskgrid-sandbox:latest`。
5. **Nginx 反代 + 静态文件**：
```bash
curl http://localhost:8080/
curl -I http://localhost:8080/static/rest_framework/css/bootstrap.min.css
curl -I http://localhost:8080/admin/login/
```
应都 200。
6. **注册登录走 8080**，token 存 `set TOKEN=...`：
```bash
curl -X POST http://localhost:8080/api/v1/auth/register/ -H "Content-Type: application/json" -H "Accept: application/json" -d "{\"username\":\"deploy1\",\"email\":\"d@example.com\",\"password\":\"deploy12345\"}"
curl -X POST http://localhost:8080/api/v1/auth/login/ -H "Content-Type: application/json" -H "Accept: application/json" -d "{\"username\":\"deploy1\",\"password\":\"deploy12345\"}"
```
7. **建任务验证沙箱真跑**（带 sleep 制造观察窗口）：
```bash
curl -X POST http://localhost:8080/api/v1/tasks/ -H "Content-Type: application/json" -H "Accept: application/json" -H "Authorization: Bearer %TOKEN%" -d "{\"name\":\"dood-check\",\"code\":\"import time; time.sleep(5); print('prod-sandbox-ok')\"}"
```
建完立刻在宿主 `docker ps` → 应看到一次性 `taskgrid-sandbox:latest` 容器。随后 GET 任务详情 → `status: success`、output 含 `prod-sandbox-ok`。
8. **ES 日志链路**：`curl "http://localhost:8080/api/v1/logs/search/?q=prod-sandbox" -H "Accept: application/json" -H "Authorization: Bearer %TOKEN%"`
9. **节点在线**（建 admin 后看节点列表）：
```bash
docker compose -f docker-compose.prod.yml exec web python manage.py shell -c "from apps.users.models import User; User.objects.create_superuser('admin','a@example.com','adminpass12345')"
curl -X POST http://localhost:8080/api/v1/auth/login/ -H "Content-Type: application/json" -d "{\"username\":\"admin\",\"password\":\"adminpass12345\"}"
```
10. **验证 gunicorn 多进程**：`docker compose -f docker-compose.prod.yml exec web ps aux | grep gunicorn` → 1 master + 3 worker
11. 收尾：`docker compose -f docker-compose.prod.yml down`（保留卷）；`down -v` 清卷

## 完成标准

- [x] 一条命令起整套集群（6 服务全 healthy）
- [x] worker 容器能操作宿主 docker（DooD 预检 `ping: True`）
- [x] Nginx 反代 8080 通，静态文件 200
- [x] 走 8080 完成注册/登录/建任务全链路，任务成功
- [x] 沙箱容器真实执行（任务 duration 5.44s + success + output 佐证）
- [x] ES 日志可搜、节点在线
- [x] gunicorn 多进程运行

## 验证记录（2026-08-04）

- 6 服务全 `Up (healthy)`（postgres/redis/elasticsearch/web/worker/nginx）
- **DooD 预检**：`exec worker python -c "import docker; c.docker.from_env()..."` → `ping: True`，镜像列表含 `taskgrid-sandbox:latest`
- Nginx：`curl http://localhost:8080/` → 200；`bootstrap.min.css` → 200；`/admin/login/` → 200
- 全链路（走 8080）：注册 deploy1 → 登录 → 建任务 `dood-check`（sleep 5s）→ **success**，output `prod-sandbox-ok`，duration 5.44s
- ES 日志：`/api/v1/logs/search/?q=prod-sandbox` → count:1 命中
- 节点：`celery@58daef4268b2` **online**，心跳正常
- gunicorn：日志 3 行 `Booting worker with pid: 9/10/11`（1 master + 3 worker）
- 坑（PowerShell）：`curl` 是 `Invoke-WebRequest` 别名，`-I` 会报"为 Uri 参数提供值"，要用 `curl.exe`；`python:3.12-slim` 没有 `ps` 命令，验证 gunicorn 用 `docker compose logs web | grep "booting worker"`

完成后告诉我，进入阶段 8：pytest 测试、代码规范、面试包装。
