"""Docker 沙箱执行器。

每个任务在一个一次性容器中隔离执行，通过资源限制防止恶意/失控代码
影响宿主机器。
"""

import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

import docker

logger = logging.getLogger(__name__)

# OOM 被内核 kill 时的退出码
OOM_EXIT_CODE = 137


@dataclass
class SandboxResult:
    exit_code: int | None = None
    output: str = ""
    error: str = ""
    timed_out: bool = False
    oom: bool = False
    duration: float = 0.0

    @property
    def success(self):
        return self.exit_code == 0


class SandboxExecutor:
    """使用 Docker API 执行用户代码，强制资源与网络隔离。"""

    def __init__(self, client=None):
        self.client = client or docker.from_env()

    def ensure_image(self, image=None):
        image = image or settings.SANDBOX_IMAGE
        try:
            self.client.images.get(image)
        except docker.errors.ImageNotFound:
            logger.info("Pulling sandbox image %s", image)
            self.client.images.pull(image)

    def execute(self, code, timeout=None, mem_limit=None, cpus=None, network_disabled=None):
        """执行一段 Python 代码，返回 SandboxResult。"""
        timeout = timeout or settings.SANDBOX_TIMEOUT
        mem_limit = mem_limit or settings.SANDBOX_MEM_LIMIT
        cpus = cpus or settings.SANDBOX_CPU
        network_disabled = (
            settings.SANDBOX_NETWORK_DISABLED if network_disabled is None else network_disabled
        )

        container = None
        start = time.monotonic()
        output = ""
        exit_code = None

        try:
            # ensure_image 放 try 内：镜像 pull 失败时也返回错误 result，而不是抛异常
            self.ensure_image()
            container = self.client.containers.run(
                settings.SANDBOX_IMAGE,
                command=["python", "-c", code],
                detach=True,
                user="sandbox",
                working_dir="/sandbox",
                read_only=True,
                tmpfs={"/tmp": "size=64m"},
                pids_limit=64,
                mem_limit=mem_limit,
                memswap_limit=mem_limit,
                nano_cpus=int(cpus * 1_000_000_000),
                network_disabled=network_disabled,
                environment={"PYTHONUNBUFFERED": "1"},
            )

            # wait(timeout) 超时视为任务超时。
            # 注意：Windows 命名管道上抛 ConnectionError，TCP 上抛 ReadTimeout，
            # 两种都要捕获，否则超时会被当成普通异常导致状态错误。
            try:
                wait_result = container.wait(timeout=timeout)
            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                logger.warning("Task timed out after %ss, killing container", timeout)
                try:
                    container.kill()
                except docker.errors.APIError:
                    pass  # 容器可能已自行退出
                wait_result = container.wait()
                return SandboxResult(
                    exit_code=wait_result.get("StatusCode", -1),
                    output=self._get_logs(container),
                    timed_out=True,
                    duration=time.monotonic() - start,
                )

            exit_code = wait_result.get("StatusCode", -1)
            output = self._get_logs(container)

            return SandboxResult(
                exit_code=exit_code,
                output=output,
                oom=exit_code == OOM_EXIT_CODE,
                duration=time.monotonic() - start,
            )

        except docker.errors.ImageNotFound:
            return SandboxResult(
                error="沙箱镜像不存在", exit_code=-1, duration=time.monotonic() - start
            )
        except docker.errors.APIError as exc:
            logger.error("Docker API error: %s", exc)
            return SandboxResult(
                error=f"Docker API 错误: {exc}", exit_code=-1, duration=time.monotonic() - start
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except docker.errors.APIError:
                    logger.exception("Failed to remove container %s", container.id)

    @staticmethod
    def _get_logs(container):
        """同时取 stdout 和 stderr，合并返回。"""
        try:
            logs = container.logs(stdout=True, stderr=True)
            return logs.decode("utf-8", errors="replace")
        except docker.errors.APIError:
            logger.exception("Failed to read logs from container %s", container.id)
            return ""
