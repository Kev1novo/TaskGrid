# 阶段 0：环境准备 + Django 速成

> 目标：搭好开发环境，通过官方教程建立 Django 的核心概念，为阶段 1 项目骨架做准备。

## 环境状态

| 工具 | 状态 |
|---|---|
| Python 3.12.6 | ✅ |
| Git 2.33.1 | ✅ |
| Docker Desktop 29.6.2 | ✅（CLI 未在 PATH，需重启终端或用全路径） |
| 虚拟环境 `.venv` + Django 6.0 | ✅ |

激活虚拟环境（Git Bash）：
```bash
source .venv/Scripts/activate
```

## 任务 1：启动 PostgreSQL 和 Redis 开发容器

> 注意：Docker Desktop 安装后若 `docker` 命令提示不存在，**完全关闭当前终端并重新打开**即可，或者临时使用完整路径。

如果你当前终端 `docker ps` 报 `command not found`，先临时加 PATH：
```bash
export PATH="/c/Users/EDY/AppData/Local/Programs/DockerDesktop/resources/bin:$PATH"
```

然后启动容器：
```bash
docker run -d --name taskgrid-pg -e POSTGRES_PASSWORD=dev123 -e POSTGRES_DB=taskgrid -p 5432:5432 postgres:16
docker run -d --name taskgrid-redis -p 6379:6379 redis:7
```

验证：
```bash
docker ps   # 应看到两个容器在运行
```

## 任务 2：Django 官方教程（重点，约 3~5 小时）

跟做官方教程 Part 1~4（polls 投票应用）：
https://docs.djangoproject.com/zh-hans/6.0/intro/tutorial01/

在 `learning/polls_tutorial/` 目录下做，与正式项目隔离。

**不必逐行照抄，重点理解这 6 个概念**（做完要能用自己的话讲出来）：

1. **MTV 模式** — Model / Template / View 各管什么，请求从 URL 到响应的完整链路
2. **URL 路由** — `urls.py` 如何把 URL 映射到视图，`include()` 的作用
3. **ORM** — Model 定义如何变成数据库表，QuerySet 常用操作（filter/get/exclude）
4. **迁移** — `makemigrations` 和 `migrate` 分别在做什么
5. **Admin** — 一行注册获得后台管理，理解 Django "batteries included" 的风格
6. **视图两种写法** — 函数视图 vs 类视图（为 DRF 的 APIView/ViewSet 打基础）

## 任务 3：自检问题

做完教程后回答（写在本文件下方或口述给我）：

1. 一个请求从浏览器到数据库再返回，经过了 Django 的哪些组件？
2. `python manage.py migrate` 执行的瞬间发生了什么？
3. 为什么要用迁移而不是直接改数据库表结构？
### 问题 1：一个请求从浏览器到数据库再返回，经过了 Django 的哪些组件？

这是一个经典的 Django 请求生命周期，流程如下：

1.  **Web 服务器（WSGI/ASGI）**：请求到达服务器（如 Nginx + uWSGI 或 Gunicorn），服务器将 HTTP 请求转换为符合 WSGI/ASGI 标准的请求对象，交给 Django。

2.  **中间件（Middleware）**：请求进入 Django 后，会依次穿过配置在 `MIDDLEWARE` 列表中的中间件。每个中间件可以在请求到达视图前进行处理（如身份验证、日志记录、会话管理等）。

3.  **URL 路由（URLResolver）**：Django 根据 `urls.py` 文件中的路由配置，将请求的 URL 路径与对应的**视图函数或类**进行匹配。如果匹配失败，返回 404。

4.  **视图（View）**：匹配成功的视图函数/类被调用，开始处理请求。
    *   它可能从请求对象中获取参数、表单数据等。
    *   视图的核心任务是**业务逻辑处理**，比如数据校验、权限检查等。

5.  **数据库操作（ORM）**：当视图需要读取或写入数据时，会通过 Django 的 **ORM（对象关系映射）** 与数据库交互。
    *   ORM 将 Python 代码（如 `User.objects.filter(age=18)`）转换为 SQL 语句。
    *   通过数据库连接（`DATABASES` 配置），执行 SQL 并获取结果。
    *   查询结果被映射为 Python 对象（Model 实例），返回给视图。

6.  **模板渲染（Template）**（可选）：如果视图需要返回 HTML 页面，它会将数据传递给模板引擎（Django Template 或 Jinja2），渲染出最终的 HTML 字符串。

7.  **响应对象（Response）**：视图最终返回一个 `HttpResponse` 对象（或子类，如 `JsonResponse`）。这个响应对象携带了状态码、头部信息和正文内容。

8.  **中间件反向处理**：响应对象会再次穿过**相同顺序的中间件**，但这次是反向执行中间件的 `process_response` 方法，进行最终的后处理（如添加额外的响应头）。

9.  **Web 服务器返回响应**：Django 将响应对象交给 WSGI/ASGI 服务器，由服务器将其转换为 HTTP 响应并发送回浏览器。

> **关键路径总结**：`请求 → 中间件(前) → URL路由 → 视图 → (ORM → 数据库) → (模板渲染) → 响应对象 → 中间件(后) → 响应`。

---

### 问题 2：`python manage.py migrate` 执行的瞬间发生了什么？

`migrate` 命令是 Django 迁移系统的核心，执行瞬间发生了以下一系列事情：

1.  **创建迁移计划**：
    *   Django 读取所有已安装应用的 `migrations` 目录下的迁移文件。
    *   同时查询数据库中的 `django_migrations` 表，获取已执行过的迁移记录（迁移文件名及其应用时间）。
    *   对比两者，计算出**待执行的迁移列表**（即那些存在迁移文件但尚未在 `django_migrations` 表中记录的操作）。

2.  **预检和依赖排序**：
    *   分析迁移文件中的 `dependencies` 属性，确保迁移按正确的顺序执行（例如，A 应用依赖 B 应用的表，则 B 的迁移必须先执行）。
    *   构建一个有向无环图（DAG），确定最终的执行顺序。

3.  **生成 SQL 语句**：
    *   对于每个待执行的迁移文件，Django 调用其 `operations` 列表（包含 `CreateModel`、`AddField`、`AlterField` 等操作）。
    *   通过 `schema_editor`（数据库适配器），将每个操作转换为针对当前数据库后端（如 PostgreSQL、MySQL）的**具体 SQL 语句**。

4.  **在数据库事务中执行 SQL**（大多数数据库支持）：
    *   在事务中，按顺序执行生成的 SQL 语句。这包括创建新表、添加列、修改字段类型等。
    *   如果某个 SQL 执行失败，事务会**回滚**，数据库回到执行前的状态，并抛出错误。

5.  **记录迁移历史**：
    *   所有 SQL 执行成功后，Django 在 `django_migrations` 表中为每个刚执行的迁移**插入一条新记录**，记录应用名称、迁移文件名和迁移时间。

6.  **后处理信号**：
    *   如果迁移涉及模型创建，可能触发 `post_migrate` 信号，用于执行一些初始化数据操作（如创建默认权限组）。

> **简单来说**：`migrate` 的本质是 **“将迁移文件中的 Python 操作，翻译成数据库能懂的 SQL 并执行，最后打上执行标记”**。

---

### 问题 3：为什么要用迁移而不是直接改数据库表结构？

这是 Django 设计中一个极其重要的工程实践。直接修改数据库表结构（手动 DDL）会带来以下问题：

| 对比维度 | 使用 Django 迁移 | 直接修改数据库表结构 |
| :--- | :--- | :--- |
| **版本控制** | 迁移文件与代码一起提交到 Git，完整记录了数据库的**变更历史**，可追溯任意时间点的数据结构。 | 没有变更记录，团队不知道谁在什么时候改了什么，数据结构历史一片混沌。 |
| **团队协作** | 每个开发者只需拉取代码并运行 `migrate`，即可同步最新的数据库结构，**保证开发环境一致**。 | 各自手工执行 SQL，极易出现遗漏或顺序错误，导致“在我机器上能跑”的问题。 |
| **回滚能力** | Django 提供了 `migrate <app> <migration_name>` 命令，可以**轻松回退**到任意历史版本。 | 回滚非常困难，要么需要手动编写逆向 SQL，要么依赖备份还原，风险极高。 |
| **数据安全** | 迁移操作在事务中执行，失败自动回滚；复杂的表变更（如添加非空字段）会在迁移文件中要求你提供默认值，**防止生产事故**。 | 直接执行 ALTER TABLE 可能锁表导致服务不可用，且错误操作无法恢复。 |
| **环境迁移** | 在测试、预发布、生产等不同环境上，只需运行同一个迁移命令，**自动适配不同数据库**（SQLite/PostgreSQL/MySQL）。 | 需要为每个环境编写不同的 SQL 脚本，且手动执行容易出错。 |
| **ORM 同步** | 迁移文件与 Model 定义保持同步，Django ORM 能准确理解当前数据库结构。 | Model 定义与真实数据库脱节，ORM 查询可能因为字段缺失或类型不匹配而报错。 |

> **核心结论**：迁移的本质是**将数据库变更“代码化”**，使其成为项目代码资产的一部分，实现了数据库结构的**可版本化、可协作、可回滚、可自动化部署**。这是现代 Web 开发中数据库管理的最佳实践，绝非可有可无。

## 完成标准

- [ ] `docker ps` 能看到 postgres 和 redis 容器
- [ ] polls 教程项目能跑通投票流程
- [ ] 能回答上面 3 个自检问题

完成后告诉我，进入阶段 1（项目骨架 + DRF 认证）。
