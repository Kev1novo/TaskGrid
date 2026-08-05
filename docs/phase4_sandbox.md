# 阶段 4：Docker 沙箱执行器

## 已完成内容

### 1. 沙箱镜像
- [docker/sandbox/Dockerfile](docker/sandbox/Dockerfile) — 基于 `python:3.12-slim`
  - 创建非 root 的 `sandbox` 用户，任务代码以它运行
  - `/sandbox` 工作目录只读

### 2. 沙箱执行器
- [apps/sandbox/executor.py](apps/sandbox/executor.py) — `SandboxExecutor`
  - **资源限制**：内存 256m、1 核 CPU、最多 64 个进程
  - **文件系统隔离**：根文件系统只读，只允许写 `/tmp`（64m tmpfs）
  - **网络隔离**：默认禁用网络（`network_disabled`）
  - **超时强杀**：超过 30 秒自动 kill 容器
  - **日志收集**：合并 stdout/stderr
  - **结果分类**：正常退出 / 超时 / OOM / 异常退出
  - 每次执行后容器强制删除，不留残留

### 3. 任务执行器接入
- [apps/tasks/tasks.py](apps/tasks/tasks.py) — 删除模拟执行，改为真实沙箱执行
- 超时 → `timeout` 状态；内存超限 → `failed`；代码异常 → `failed` + 错误信息

### 4. 配置
- [config/settings/base.py](config/settings/base.py) — 沙箱镜像、超时、内存、CPU、网络开关

### 5. 构建脚本
- Windows：`scripts/build_sandbox.bat`
- Git Bash：`scripts/build_sandbox.sh`

## 学习与验证

### 重点学习点
1. **容器隔离的四个维度**：网络（`network_disabled`）、文件系统（`read_only` + tmpfs）、资源（mem_limit/cpus/pids_limit）、进程（非 root 用户）
2. **Docker SDK 用法**：`containers.run(detach=True)` + `wait(timeout)` + `logs()` + `remove(force=True)`
3. **超时实现**：`wait(timeout)` 抛 `ReadTimeout` 后 kill，而不是靠宿主机杀死进程
4. **OOM 检测**：退出码 137 = 被内核 kill

### 验证步骤

1. 构建沙箱镜像（首次需要，之后不用）：
```bash
scripts\build_sandbox.bat
```

2. 确认镜像存在：
```bash
docker images
# 应看到 taskgrid-sandbox:latest
```

3. 重启 Celery worker（因为代码改了，要重启 worker 才能加载新代码）：
```bash
# 关掉旧的 Celery Worker 窗口，重新跑：
.\scripts\start_celery.bat
```

4. 用 Django 创建任务，测试以下场景：

镜像构建成功，worker 已重启。下面手把手教你在 Django 里创建任务测试沙箱。

先确认三样东西都在跑：

Django（端口 8000，curl 登录能通就说明在）
Celery Worker 窗口（刚重启的那个）
taskgrid-sandbox 镜像（上面 docker images 已确认）
第 1 步：登录拿 token

curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"password\":\"password123\"}"
返回 JSON 里 access 字段的值就是 token。把它复制出来，后面每个请求都要用到。

第 2 步：测试场景 A（正常执行）
创建任务：


curl -X POST http://127.0.0.1:8000/api/v1/tasks/ -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d "{\"name\":\"sandbox-ok\",\"code\":\"print('hello from sandbox')\"}"
创建后立刻查看这个任务的当前状态（注意替换 <task_id> 为返回的 id）：


curl http://127.0.0.1:8000/api/v1/tasks/<task_id>/ -H "Authorization: Bearer <token>"
因为沙箱启动容器要几秒，第一次查可能还是 running。等 5 秒再查一次，应该看到：


"status": "success",
"result": {
    "output": "hello from sandbox\n",
    "duration": 1.2
}
判断标准：status = success 且 result.output 含 hello from sandbox，场景 A 通过。

第 3 步：测试场景 B（代码报错）

curl -X POST http://127.0.0.1:8000/api/v1/tasks/ -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d "{\"name\":\"sandbox-error\",\"code\":\"raise ValueError('boom')\"}"
等几秒后查询，应看到：


"status": "failed",
"error_message": "Traceback (most recent call last):\n...\nValueError: boom"
判断标准：status = failed，error_message 含 ValueError: boom。

第 4 步：测试场景 C（死循环超时）

curl -X POST http://127.0.0.1:8000/api/v1/tasks/ -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d "{\"name\":\"sandbox-timeout\",\"code\":\"while True: pass\",\"params\":{\"timeout\":5}}"
这个任务会执行 5 秒后被沙箱强杀。等 10 秒后查询，应看到：


"status": "timeout"
判断标准：status = timeout。这是本项目最有说服力的功能——失控代码被自动终止，宿主没事。

第 5 步：测试场景 E（隔离性验证）

curl -X POST http://127.0.0.1:8000/api/v1/tasks/ -H "Content-Type: application/json" -H "Authorization: Bearer <token>" -d "{\"name\":\"sandbox-escape\",\"code\":\"import os; print(os.listdir('/')); open('/etc/hosts','w').write('x')\"}"
os.listdir('/') 会列出沙箱容器自己的根目录（你应该看不到 Windows、Program Files 之类）。写 /etc/hosts 会失败——因为根文件系统只读，任务会报 failed。

判断标准：输出里没有宿主机文件；PermissionError 说明只读隔离生效。

## 完成标准

- [ ] 构建出 taskgrid-sandbox 镜像
- [ ] 正常代码执行成功，返回输出
- [ ] 报错代码返回错误信息
- [ ] 死循环被超时强杀
- [ ] 只读文件系统 / 禁用网络生效

完成后告诉我，进入阶段 5：节点管理（Worker 注册/心跳/故障转移）。
