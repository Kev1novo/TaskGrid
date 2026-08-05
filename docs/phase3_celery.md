# 阶段 3：Celery + Redis 异步调度

## 已完成内容

### 1. Celery 接入
- [config/celery.py](config/celery.py) — Celery 应用初始化
- [config/__init__.py](config/__init__.py) — Django 启动时加载 Celery
- [config/settings/base.py](config/settings/base.py) — Redis broker/result backend 配置

### 2. 任务执行
- [apps/tasks/tasks.py](apps/tasks/tasks.py) — `execute_task` 异步任务
  - 自动从 `pending` → `running` → `success/failed`
  - 记录 `worker_id` 和起止时间
  - 失败自动重试 3 次
  - 阶段 3 用本地模拟执行，阶段 4 替换为 Docker 沙箱

### 3. 自动派发
- [apps/tasks/views.py:34](apps/tasks/views.py#L34) — 创建任务后自动 `execute_task.delay(task.id)`

### 4. 监控
- Flower：`http://127.0.0.1:5555`
- 启动脚本：
  - Windows：`scripts/start_celery.bat`
  - Git Bash：`scripts/start_celery.sh`

## 学习与验证

### 重点学习点
1. **Celery 架构**：Producer（Django Web）→ Broker（Redis）→ Worker（独立进程）→ Result Backend（Redis）
2. **`shared_task` vs `@app.task`**：Django 项目里用 `shared_task` 更解耦
3. **bind=True**：任务函数第一个参数是 `self`，可访问 `self.request.hostname/retries`
4. **自动重试**：`max_retries` + `self.retry(exc=exc)`
5. **Windows 坑**：Celery 默认 prefork 池在 Windows 上不稳定，用 `-P solo` 或 `-P threads`

### 验证步骤

1. 确保 Redis 容器在运行：
```bash
docker ps
```

2. 启动 Celery worker 和 Flower（开新终端）：
```bash
# Windows
.\scripts\start_celery.bat

# Git Bash
./scripts/start_celery.sh
```

3. 打开 Flower：`http://127.0.0.1:5555`

4. 启动 Django 开发服务器：
```bash
python manage.py runserver
```

5. POST 创建任务：
```bash
curl -X POST http://127.0.0.1:8000/api/v1/tasks/ \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"name":"celery-test","code":"print(1+1)","priority":3}'
```

6. 观察：
   - Flower 里出现任务并执行
   - 任务状态从 `pending` → `running` → `success`
   - GET `/api/v1/tasks/` 能看到 `result` 和 `duration`

7. 测试失败重试：创建一个会失败的代码，例如 `raise Exception('boom')`，观察 Flower 里重试 3 次后变 `failed`。

## 完成标准

- [ ] Worker 能正常启动不报错
- [ ] 创建任务后状态自动流转
- [ ] Flower 能看到任务执行记录
- [ ] 失败任务会重试 3 次

完成后告诉我，进入阶段 4：Docker 沙箱执行器。
