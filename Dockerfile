# 阶段 7：web + worker 共用应用镜像
# 本地 venv 依赖用 requirements.txt（含 pywin32，Windows 专用）；
# 容器依赖用 requirements-prod.txt（无 pywin32，加了 gunicorn）
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

# 非 root 运行：web 以 app 用户跑 gunicorn
RUN addgroup --system app && adduser --system --ingroup app app

WORKDIR /app

# 先装依赖（requirements 不变则复用该镜像层，加速重建）
COPY requirements-prod.txt ./
RUN pip install -r requirements-prod.txt

# 复制源码（.dockerignore 控制体积）
COPY . .

# 静态输出目录：保证命名卷首次挂载时属主为 app，collectstatic 才写得进去
RUN mkdir -p /app/staticfiles && chown -R app:app /app/staticfiles

USER app

EXPOSE 8000

# 默认命令 = web（worker 由 compose 用 command 覆盖）
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "2", "--access-logfile", "-", "--error-logfile", "-"]
