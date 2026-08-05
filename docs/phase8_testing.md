# 阶段 8：pytest 测试 + 代码规范 + 文档

## 已完成内容

### 1. 测试工具链
- 依赖在 [requirements-dev.txt](../requirements-dev.txt)（dev 专用，生产镜像不装）：pytest / pytest-django / pytest-cov / black / isort / flake8 / pre-commit

### 2. 测试配置
- [config/settings/test.py](../config/settings/test.py)：测试专用 settings，`CELERY_TASK_ALWAYS_EAGER=True` 让 Celery 同步执行（不发真实 Redis 队列）
- [pyproject.toml](../pyproject.toml)：pytest 入口 + black/isort 配置（line-length 100）
- [.flake8](../.flake8)：flake8 配置
- [conftest.py](../conftest.py)：公共 fixtures —— `api_client`（DRF APIClient）、`user`/`admin`/`auth_client`（JWT）、`fake_sandbox`（mock 沙箱执行器）、`fake_es`（mock ES client）

### 3. 测试用例（77 个，覆盖率 91%）

| 模块 | 文件 | 覆盖点 |
|---|---|---|
| users | test_models / test_permissions / test_api | `User.is_admin()`、三个权限类全分支、注册/登录/刷新/profile/用户列表接口 |
| tasks | test_models / test_api / test_celery_task | 状态机全合法路径 + 非法转移、CRUD owner 隔离、status/cancel action、Celery 任务四状态流转 |
| nodes | test_services | 节点注册幂等、心跳上报（mock psutil）、超时离线检测、两种调度策略 |
| sandbox | test_executor | 成功/失败/OOM/超时强杀/镜像缺失/API 错误、`SandboxResult.success` |
| logs | test_services / test_views | ES 索引幂等创建、文档字段、降级设计、检索过滤条件、owner 隔离、503 |

**Mock 边界**（纯逻辑不碰真实 I/O）：psutil（心跳）、docker SDK（沙箱）、ES client（日志）、Celery delay（API 测试阻断真实派发）。

### 4. 代码规范
- black + isort 全量格式化现有代码，修复所有 flake8 报错（未用 import、E402 模块级 import 位置等）
- [.pre-commit-config.yaml](../.pre-commit-config.yaml)：black / isort / flake8 三个钩子
- `git init` + `pre-commit install`，提交前自动检查

### 5. 文档
- [README.md](../README.md)：项目介绍、架构、快速开始、API 摘要（面试展示用）
- [docs/interview_prep.md](interview_prep.md)：简历描述 + 常考面试题 Q&A

## 学习与验证

### 重点学习点
1. **pytest vs Django TestCase**：pytest 用 `fixture` 管理依赖（`db` 提供数据库、`monkeypatch` 打补丁），比 Django 的 setUp/tearDown 更灵活；pytest-django 自动建测试库（`test_taskgrid`）
2. **Mock 让测试不碰真实 I/O**：核心思路——测试纯逻辑，把外部边界（Docker/ES/psutil/Celery）都替换成可控假对象。`fake_sandbox` 让 Celery 任务测试能模拟任意执行结果
3. **Celery 测试**：`CELERY_TASK_ALWAYS_EAGER` 让 `.delay()` 同步执行；但 API 测试要 **block** 它（`monkeypatch` 掉 `execute_task.delay`），否则会真的去跑 Docker
4. **DRF 越权返回 404 而非 403**：`get_queryset` 按 owner 过滤后，别人的资源对普通用户查不到 → 404（比 403 更安全，不泄露资源存在性）
5. **flake8 exclude 的坑**：`exclude=migrations` 只在目录遍历时生效；pre-commit 显式传文件路径时要写 `*migrations*`（fnmatch 全路径匹配）
6. **测试暴露了真实 bug**：沙箱 `ensure_image()` 原在 try 外，镜像 pull 失败会抛异常而不是返回错误 result（`except ImageNotFound` 是死代码）。已修复移入 try

### 验证步骤

1. 启动依赖容器（测试库要用 Postgres）：
```bash
docker compose -f docker-compose.dev.yml up -d postgres
```
2. 跑测试：
```bash
pytest
```
预期：77 passed，覆盖率 ≥70%。
3. 规范检查：
```bash
black --check . && isort --check . && flake8 .
```
4. 提交前钩子：
```bash
pre-commit run --all-files
```

## 完成标准

- [x] pytest 全绿（77 passed）
- [x] 覆盖率 91%（≥70% 目标）
- [x] black / isort / flake8 全过
- [x] pre-commit 钩子通过
- [x] README / phase8 / 面试文档齐全
- [x] 格式化未破坏功能（dev 集群可跑冒烟）

## 验证记录（2026-08-04）

- `pytest` → **77 passed**，`TOTAL 1017 91%`
- `black --check` → 68 files unchanged；`isort --check` → clean；`flake8` → clean
- `pre-commit run --all-files` → black / isort / flake8 全 Passed
- 测试暴露并修复 1 个真实 bug（sandbox ensure_image 位置）

## 全部 8 个阶段完成 ✅

项目从零到完整分布式系统：认证 → 任务状态机 → Celery 异步 → Docker 沙箱 → 节点调度/故障转移 → ES 日志 → 集群化部署 → 测试与规范。
