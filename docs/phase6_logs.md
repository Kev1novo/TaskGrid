# 阶段 6：Elasticsearch 日志检索

## 已完成内容

### 1. 启动 ES 容器
- [docker-compose.dev.yml](docker-compose.dev.yml) 新增 `elasticsearch` 服务（8.15.3，单节点，禁用安全）

### 2. 日志服务层
- [apps/logs/services.py](apps/logs/services.py)
  - `ensure_index()` — 首次写入时自动创建 `tasklogs` 索引（含 mapping）
  - `index_task_log()` — 任务执行结束后把日志写入 ES
  - `search_logs()` — 按关键词/任务/用户/状态检索，时间倒序
  - **降级设计**：ES 写入/查询失败只记日志，绝不影响任务主流程（ES 是辅助系统）

### 3. 日志检索 API
| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/logs/search/` | 全文检索日志 |
| 参数 | `q` | 关键词（匹配 output/error/task_name） |
| 参数 | `task_id` | 按任务过滤 |
| 参数 | `status` | 按状态过滤 |

权限：普通用户只能搜**自己任务**的日志；管理员可搜全部。

### 4. 索引 mapping 要点（学习重点）
```json
{
  "task_id": {"type": "keyword"},   // 精确匹配，用于过滤
  "output": {"type": "text"},       // 全文检索，用于 match
  "status": {"type": "keyword"},
  "created_at": {"type": "date"}    // 时间倒序排序
}
```
`keyword` 和 `text` 的区别：keyword 支持精确 term 查询和排序；text 支持全文模糊匹配。**这是 ES 设计索引时最先要决定的**。

## 学习与验证

### 重点学习点
1. **ES vs 关系型数据库**：ES 解决"海量日志的全文检索"，不解决"强事务的精确查询"。日志场景用它，业务数据用 PostgreSQL
2. **倒排索引**：ES 把文本切词后建倒排表，查询时 O(1) 命中词条，所以全文检索快
3. **mapping 一旦建立很难改**：生产环境要预先设计好字段类型
4. **降级容错**：辅助系统挂掉不能拖垮主流程，这是微服务里的核心思想

### 验证步骤

1. **启动 ES 容器**（第一次要拉镜像，约 1~2 分钟）：
```bash
docker compose -f docker-compose.dev.yml up -d
```

2. 确认 ES 健康（等它变 green/yellow）：
```bash
curl http://127.0.0.1:9200/_cluster/health
```

3. **重启 Celery worker**（代码改了要重启）：
```bash
scripts\start_celery.bat
```

4. 创建几个任务制造日志（正常 + 报错各一个）：
```cmd
curl -X POST http://127.0.0.1:8000/api/v1/tasks/ -H "Content-Type: application/json" -H "Accept: application/json" -H "Authorization: Bearer <token>" -d "{\"name\":\"log-test\",\"code\":\"print('hello es')\"}"
curl -X POST http://127.0.0.1:8000/api/v1/tasks/ -H "Content-Type: application/json" -H "Accept: application/json" -H "Authorization: Bearer <token>" -d "{\"name\":\"log-error\",\"code\":\"raise Exception('es error case')\"}"
```

5. **全文检索**（alice 只能搜到自己的）：
```cmd
curl "http://127.0.0.1:8000/api/v1/logs/search/?q=hello" -H "Accept: application/json" -H "Authorization: Bearer <token>"
```
应命中 log-test 的日志。

```cmd
curl "http://127.0.0.1:8000/api/v1/logs/search/?q=error" -H "Accept: application/json" -H "Authorization: Bearer <token>"
```
应命中 log-error 的日志（含 traceback）。

6. **按状态过滤**：
```cmd
curl "http://127.0.0.1:8000/api/v1/logs/search/?status=success" -H "Accept: application/json" -H "Authorization: Bearer <token>"
```

7. **直接看 ES 里的原始文档**（体会 ES 的存储结构）：
```cmd
curl "http://127.0.0.1:9200/tasklogs/_search?pretty=true&size=3"
```

8. **权限验证**：用 alice 查 admin 的任务日志（task_id 传 admin 创建的任务 id），应只返回自己的或不返回。

## 完成标准

- [x] ES 容器健康，索引自动创建
- [x] 任务执行后日志出现在 ES
- [x] `/api/v1/logs/search/?q=` 能全文检索
- [x] 普通用户看不到别人的日志

## 验证记录（2026-08-04）

- `q=hello` → 命中 `log-test`（success，output: `hello es`）
- `q=error` → 命中 `log-error`（failed，含 traceback）
- `?status=success` → 只返回 success 的日志
- 用 bob（新注册普通用户）搜 `q=hello` → `count: 0`，隔离生效
- 坑：命令行过长粘贴时换行会截断 `Authorization` header 导致"身份认证信息未提供"，长 token 建议用环境变量 `set TOKEN=...` + `%TOKEN%`

完成后告诉我，进入阶段 7：集群化部署（Nginx + Gunicorn + docker-compose）。
