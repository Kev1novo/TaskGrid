# 阶段 2：任务模块 CRUD + 状态机 + Swagger

## 已完成内容

### 1. 新增依赖
- `drf-spectacular` — 自动生成 OpenAPI / Swagger 文档
- `django-filter` — 列表过滤

### 2. Task 模型（[apps/tasks/models.py](apps/tasks/models.py)）
- UUID 主键
- 状态：`pending` → `running` → `success/failed/timeout`，支持 `cancelled`
- 优先级：1 低 / 2 普通 / 3 高 / 4 紧急
- 任务类型、代码/命令、参数、执行节点、结果、起止时间
- `transit()` 方法实现状态机校验

### 3. RESTful API（[apps/tasks/views.py](apps/tasks/views.py)）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST | `/api/v1/tasks/` | 任务列表 / 创建任务 |
| GET/PUT/PATCH/DELETE | `/api/v1/tasks/{id}/` | 单任务 CRUD |
| POST | `/api/v1/tasks/{id}/status/` | 更新任务状态（状态机校验） |
| POST | `/api/v1/tasks/{id}/cancel/` | 取消待执行的任务 |

### 4. 权限
- 普通用户只能看/操作自己的任务
- 管理员可以看所有任务
- 使用 `IsOwnerOrAdmin` 对象级权限

### 5. 过滤与排序
- 按状态、优先级、任务类型、创建时间范围过滤
- 支持 `?ordering=priority` 或 `?ordering=-created_at`

### 6. Swagger 文档
- Schema 地址：`/api/schema/`
- UI 地址：`/api/docs/`

## 学习与验证

### 重点学习点
1. **ModelViewSet + Router**：一行代码生成 6 个标准接口
2. **序列化器分场景**：创建用 `TaskCreateSerializer`，返回用 `TaskSerializer`
3. **Django-filter**：复杂查询参数如何从 URL 自动映射到 ORM
4. **状态机模式**：业务规则（哪些状态能转移到哪些）封装在模型里，而不是散落在视图

### 验证步骤

启动服务：
```bash
source .venv/Scripts/activate
python manage.py runserver
```

Swagger UI：打开浏览器访问 http://127.0.0.1:8000/api/docs/

用 Swagger 或 curl 验证：
1. 登录获取 token
2. POST `/api/v1/tasks/` 创建任务
3. GET `/api/v1/tasks/` 查看列表
4. GET `/api/v1/tasks/?status=pending` 按状态过滤
5. POST `/api/v1/tasks/{id}/status/` 传 `{"status":"running"}`，状态变为 running
6. 再传 `{"status":"running"}`，应返回 400（状态机拒绝重复转移）
7. POST `/api/v1/tasks/{id}/cancel/` 取消 pending 任务

## 完成标准

- [ ] Swagger UI 能正常打开
- [ ] 能创建任务并自动设置 `owner`
- [ ] 列表支持按状态、优先级过滤
- [ ] 状态转移符合状态机规则，非法转移返回 400
- [ ] 普通用户看不到别人的任务

完成后告诉我，进入阶段 3：Celery + Redis 异步调度。
