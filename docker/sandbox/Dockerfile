FROM python:3.12-slim

# 创建非 root 沙箱用户，任务代码以 sandbox 身份运行
RUN useradd --create-home --uid 1000 sandbox

WORKDIR /sandbox

# /sandbox 对用户只读（写入通过 tmpfs 到 /tmp）
RUN chown -R root:root /sandbox && chmod 755 /sandbox

USER sandbox
