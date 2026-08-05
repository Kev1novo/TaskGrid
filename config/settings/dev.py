from .base import *  # noqa: F401,F403

DEBUG = True

ALLOWED_HOSTS = ["*"]

DATABASES = {
    "default": env.db_url(  # noqa: F405
        "DATABASE_URL",
        default="postgres://postgres:dev123@127.0.0.1:5432/taskgrid",
    )
}
