from .base import *  # noqa: F401,F403

DEBUG = True

# 开发环境不需要强密码，base.py 不再提供默认值避免生产误用
SECRET_KEY = "django-insecure-dev-key-change-in-production"

CORS_ALLOW_ALL_ORIGINS = True  # 本地开发允许任意跨域

ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": env.db_url(  # noqa: F405
        "DATABASE_URL",
        default="postgres://postgres:dev123@127.0.0.1:5432/taskgrid",
    )
}
