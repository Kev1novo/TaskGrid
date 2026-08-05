import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F401,F403

DEBUG = False

# base.py 给 SECRET_KEY 注册了 dev fallback，env('SECRET_KEY') 永不抛错，
# 必须直接查 os.environ 强制生产显式提供
if not os.environ.get("SECRET_KEY"):
    raise ImproperlyConfigured("生产环境必须通过环境变量 SECRET_KEY 提供密钥")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")  # noqa: F405

DATABASES = {"default": env.db_url("DATABASE_URL")}  # noqa: F405
