# 阶段 5：节点管理（注册/心跳/故障转移）

## 已完成内容

### 1. Node 模型
- [apps/nodes/models.py](apps/nodes/models.py) — 节点名称、主机名、IP、状态（online/offline）、CPU/内存负载、最后心跳时间

### 2. 节点服务层
- [apps/nodes/services.py](apps/nodes/services.py)
  - `register_node()` — worker 启动时注册
  - `report_heartbeat()` — 上报心跳 + 本机负载（psutil 采集）
  - `mark_offline_if_stale()` — **故障检测**：心跳超过 60 秒未更新的节点自动标记离线
  - `select_node()` — **调度策略**（策略模式）：least_loaded 优先选择负载最低的在线节点，可扩展 round_robin

### 3. 心跳机制（重点理解）
- [apps/nodes/celery_events.py](apps/nodes/celery_events.py)
  - `worker_ready` 信号触发：节点注册 + 启动心跳线程
  - 每个 worker 进程内跑一个后台线程，每 30 秒上报一次自己的负载
  - **为什么不用 Celery beat？** beat 派发的任务会被任意 worker 消费，无法代表"本节点"的负载。心跳必须在 worker 进程内部自己上报。

### 4. 调度接入
- [apps/tasks/views.py](apps/tasks/views.py) — 创建任务时调用 `select_node()` 选择节点，把节点名写入 `worker_id`，再派发执行

### 5. 管理 API（仅管理员）
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/nodes/` | 节点列表（含心跳、负载） |
| GET | `/api/v1/nodes/{id}/` | 节点详情 |
| POST | `/api/v1/nodes/{id}/offline/` | 手动下线节点（演示故障转移） |

### 6. 管理命令
```bash
python manage.py nodes_check       # 手动触发故障检测
python manage.py reschedule_tasks  # 把离线节点上卡住的 running 任务重新调度
```

## 学习与验证

### 重点学习点
1. **心跳 vs 注册**：注册只发生一次（启动时），心跳是周期性的"活着"信号
2. **故障检测**：不依赖节点主动说"我死了"，而是靠"心跳超时"被动判定——更可靠
3. **策略模式**：`select_node(strategy=...)` 把"选哪个节点"抽象出来，加新策略只改一行调用
4. **Celery 信号**：`worker_ready` / `worker_shutdown` 是 worker 生命周期钩子

### 验证步骤

1. **迁移已执行**，代码改动后**重启 Celery worker**（心跳线程随 worker 启动）：
```bash
scripts\start_celery.bat
```

2. 等 30 秒，用 admin 账号查节点列表（admin/admin123 登录拿 token）：
```cmd
curl http://127.0.0.1:8000/api/v1/nodes/ -H "Accept: application/json" -H "Authorization: Bearer <admin_token>"
```

应看到类似：
```json
{
  "name": "celery@CHINAMI-QM6M2P1",
  "status": "online",
  "cpu_percent": 12.5,
  "mem_percent": 45.2,
  "last_heartbeat": "..."
}
```

3. **创建任务**，看 `worker_id` 字段自动填上了节点名：
```cmd
curl -X POST http://127.0.0.1:8000/api/v1/tasks/ -H "Content-Type: application/json" -H "Accept: application/json" -H "Authorization: Bearer <token>" -d "{\"name\":\"node-test\",\"code\":\"print(1)\"}"
```

### 场景 1：手动下线 + 心跳自动恢复（约 5 分钟）

4. **手动下线节点**（管理员 token）：
```cmd
curl -X POST http://127.0.0.1:8000/api/v1/nodes/1/offline/ -H "Accept: application/json" -H "Authorization: Bearer <admin_token>"
```
应返回该节点，`status` 变为 `offline`。

5. **观察心跳自动恢复**：worker 还活着，心跳线程每 30 秒上报一次并会把节点拉回在线。
   等 30~35 秒再查：
```cmd
curl http://127.0.0.1:8000/api/v1/nodes/ -H "Accept: application/json" -H "Authorization: Bearer <admin_token>"
```
应看到 `status` 又变回 `online`，且 `last_heartbeat` 是新的时间。

> **这印证了一个重要设计**：`offline` 不是永久状态，只要节点还活着、心跳继续，它就会被自动恢复。真正的故障检测靠"心跳超时"而不是手动标记。

### 场景 2：真实故障转移（约 15 分钟）

6. **模拟节点宕机**：直接**关闭 Celery Worker 窗口**（不要重启），让心跳停止。

7. **验证故障检测**：等 60 秒以上（心跳超时阈值），手动触发检查：
```bash
python manage.py nodes_check
```
应输出 `标记离线: ['celery@CHINAMI-QM6M2P1']`，此时节点真正离线。

8. **造一个"卡住"的任务**：把某任务状态改成 running 并指向已离线的节点名，模拟"节点执行一半宕机"：
```cmd
.venv\Scripts\python manage.py shell -c "from apps.tasks.models import Task; from apps.nodes.models import Node; n=Node.objects.get(status='offline'); Task.objects.filter(name='node-test').update(status='running', worker_id=n.name, started_at='now()'); print('done')"
```
（若 node-test 已执行完，可先新建一个任务再执行本命令，把 name 换成任务名）

9. **重新调度**（worker 还没起，任务只入队不执行，正好观察）：
```bash
python manage.py reschedule_tasks
```
应输出 `重新调度: <task_id>`，该任务状态被重置为 `pending`、`worker_id` 清空、重新进入队列。

10. **恢复节点**：重启 Celery worker：
```bash
scripts\start_celery.bat
```
- 节点重新注册并心跳恢复 → 30 秒内自动回 `online`
- 被重调度的任务会被消费执行 → 状态从 `pending` → `running` → `success`

> **完整故障转移链路**：节点宕机 → 心跳超时 → 标记离线 → 检测到卡住任务 → 重新入队 → 新节点接管执行。这就是分布式系统里"故障转移"的核心闭环。

## 完成标准

- [ ] 节点出现在管理 API 中，状态 online，有负载数据
- [ ] 创建任务的 `worker_id` 自动填入节点名
- [ ] 心跳停止超过 60 秒节点自动变 offline
- [ ] `reschedule_tasks` 能重新调度卡住的任务

完成后告诉我，进入阶段 6：Elasticsearch 日志检索。
