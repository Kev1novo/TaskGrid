# 阶段 1：项目骨架 + JWT 认证 + RBAC

## 已完成内容

### 1. 项目结构
```
taskgrid/
├── apps/
│   └── users/              # 用户认证与权限
├── config/
│   ├── settings/
│   │   ├── base.py         # 通用配置
│   │   ├── dev.py          # 开发环境
│   │   └── prod.py         # 生产环境
│   ├── urls.py             # 根路由
│   ├── wsgi.py
│   └── asgi.py
├── docker-compose.dev.yml  # 开发依赖容器
├── requirements.txt
├── .env.example
└── manage.py
```

### 2. 依赖
- Django 6.0 + DRF
- djangorestframework-simplejwt（JWT 登录/刷新）
- psycopg2-binary（PostgreSQL）
- django-environ（环境变量管理）
- django-cors-headers（跨域）

### 3. 用户模型
- 继承 `AbstractUser` 扩展 `role` 字段
- 两个角色：`admin` / `user`
- 提供 `is_admin()` 方法

### 4. API 接口

| 方法 | 路径 | 说明 | 权限 |
|---|---|---|---|
| POST | `/api/v1/auth/register/` | 用户注册 | 公开 |
| POST | `/api/v1/auth/login/` | 登录，返回 access/refresh token + 用户信息 | 公开 |
| POST | `/api/v1/auth/refresh/` | 刷新 access token | 公开 |
| GET | `/api/v1/auth/profile/` | 当前登录用户信息 | 需登录 |
| GET | `/api/v1/auth/users/` | 用户列表 | 仅管理员 |

## 学习与验证

### 重点学习点
1. **DRF 视图三种写法**：函数视图 `@api_view`、类视图 `APIView`、通用视图 `CreateAPIView/ListAPIView`
2. **JWT 认证流程**：access token 短期有效，refresh token 长期有效，前端自动刷新
3. **DRF 权限系统**：`AllowAny` / `IsAuthenticated` / 自定义 `BasePermission`

### 验证步骤

1. 启动开发服务器：
```bash
source .venv/Scripts/activate
python manage.py runserver
```

2. 测试注册（Windows CMD 请用单行版）：

**Git Bash / WSL：**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","email":"alice@example.com","password":"password123"}'
```

**Windows CMD（一行）：**
```cmd
curl -X POST http://127.0.0.1:8000/api/v1/auth/register/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"email\":\"alice@example.com\",\"password\":\"password123\"}"
```

3. 测试登录：

**Git Bash / WSL：**
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"password123"}'
```

**Windows CMD（一行）：**
```cmd
curl -X POST http://127.0.0.1:8000/api/v1/auth/login/ -H "Content-Type: application/json" -d "{\"username\":\"alice\",\"password\":\"password123\"}"
```

4. 用返回的 `access` token 访问个人资料：

**Git Bash / WSL：**
```bash
curl http://127.0.0.1:8000/api/v1/auth/profile/ \
  -H "Authorization: Bearer <access_token>"
```

**Windows CMD（一行）：**
```cmd
curl http://127.0.0.1:8000/api/v1/auth/profile/ -H "Authorization: Bearer <access_token>"
```

5. 管理员账号：
- 用户名：`admin`
- 密码：`admin123`

## 阶段 1 完成标准

- [ ] 注册接口能创建普通用户
- [ ] 登录接口返回 access/refresh token 和用户信息
- [ ] 带 token 能访问 `/profile/`
- [ ] 不带 token 访问 `/profile/` 返回 401
- [ ] 普通用户访问 `/users/` 返回 403
- [ ] 管理员访问 `/users/` 能拿到用户列表

完成后告诉我，进入阶段 2：任务模块 CRUD + 状态机 + Swagger。
