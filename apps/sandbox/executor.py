"""Docker 沙箱执行器。

每个任务在一个一次性容器中隔离执行，通过资源限制防止恶意/失控代码
影响宿主机器。

安全设计（四层隔离）：
  1. user="sandbox"      → 非 root 用户，不能执行需要 root 权限的操作
  2. read_only=True      → 文件系统只读（仅 /tmp 可写），改不了宿主文件
  3. network_disabled    → 禁用网络，代码发不了数据到外部
  4. 资源限制            → mem 256m / 1 CPU / 64 进程 / 30s 超时
                             超时强杀、OOM 检测（退出码 137）
"""

import logging
import time
from dataclasses import dataclass

import requests
from django.conf import settings

import docker

logger = logging.getLogger(__name__)

# 被 Linux 内核 OOM Killer 杀死的进程退出码固定为 137（128 + SIGKILL 9）
OOM_EXIT_CODE = 137


@dataclass
class SandboxResult:
    """沙箱执行结果——一个纯数据容器，用来把 Docker 容器的执行结果传回给调用者。

    字段说明：
      exit_code: 容器内进程的退出码（0=成功，非0=失败，137=OOM，-1=系统异常）
      output:    stdout + stderr 合并后的文本
      error:     系统级错误描述（不是用户代码报错，是 Docker 层面的问题）
      timed_out: 是否因为超时被强制终止
      oom:       是否因为内存超限被内核杀死
      cancelled: 是否被用户手动取消（executor 轮询到取消标记后强杀容器）
      duration:  实际执行耗时（秒）
    """

    exit_code: int | None = None
    output: str = ""
    error: str = ""
    timed_out: bool = False
    oom: bool = False
    cancelled: bool = False
    duration: float = 0.0

    @property
    def success(self):
        """exit_code=0 就是成功。"""
        return self.exit_code == 0


class SandboxExecutor:
    """使用 Docker API 执行用户代码，强制资源与网络隔离。

    用法：result = SandboxExecutor().execute(code="print('hello')", timeout=10)
    每次调用会创建一个新容器，跑完立即销毁。
    """

    def __init__(self, client=None):
        # client=None 时自动从环境变量/本机 Docker daemon 连接
        self.client = client or docker.from_env()

    def ensure_image(self, image=None):
        """确保沙箱镜像存在，不存在就拉取。"""
        image = image or settings.SANDBOX_IMAGE
        try:
            self.client.images.get(image)  # 先检查本地有没有
        except docker.errors.ImageNotFound:
            logger.info("Pulling sandbox image %s", image)
            self.client.images.pull(image)  # 没有就从 Docker Hub 拉

    def execute(
        self,
        code,
        timeout=None,
        mem_limit=None,
        cpus=None,
        network_disabled=None,
        cancel_check=None,
    ):
        """执行一段 Python 代码，返回 SandboxResult。

        参数：
          code             要执行的 Python 代码
          timeout          超时秒数（默认 30）
          mem_limit        内存限制（默认 "256m"）
          cpus             CPU 核数限制（默认 1.0）
          network_disabled 是否禁用网络（默认 True）
          cancel_check     取消回调：返回 True 时强杀容器（用于 RUNNING→CANCELLED）

        执行流程：
          1. 确保镜像存在
          2. docker run --rm --read-only --network=none --memory=256m ...
          3. 轮询 container.wait(poll_interval) → 每次检查 cancel_check()
          4. 超时/取消 → 强杀容器
          5. 取日志 → 销毁容器 → 返回结果
        """
        timeout = timeout or settings.SANDBOX_TIMEOUT
        mem_limit = mem_limit or settings.SANDBOX_MEM_LIMIT
        cpus = cpus or settings.SANDBOX_CPU
        network_disabled = (
            settings.SANDBOX_NETWORK_DISABLED if network_disabled is None else network_disabled
        )

        container = None  # 确保 finally 里可以判断是否创建了容器
        start = time.monotonic()  # 开始计时
        output = ""
        exit_code = None

        try:
            # ensure_image 放 try 内：镜像 pull 失败时也返回错误 result，而不是抛异常
            # 如果放在 try 外面，ImageNotFound 会直接炸掉整个 execute()
            self.ensure_image()

            # ——— 创建并启动容器 ———
            container = self.client.containers.run(
                settings.SANDBOX_IMAGE,
                command=["python", "-c", code],  # 用 python -c 执行代码
                detach=True,  # 后台模式，不阻塞
                user="sandbox",  # ⚠️ 非 root 用户（镜像里预建的 sandbox 用户）
                working_dir="/sandbox",
                read_only=True,  # ⚠️ 文件系统只读
                tmpfs={"/tmp": "size=64m"},  # 只有 /tmp 可写（内存文件系统，64MB）
                pids_limit=64,  # ⚠️ 最多 64 个进程（防 fork bomb）
                mem_limit=mem_limit,  # ⚠️ 内存硬限制
                memswap_limit=mem_limit,  # ⚠️ swap 也限制（等于内存时 = 禁用 swap）
                nano_cpus=int(cpus * 1_000_000_000),  # ⚠️ CPU 限制（纳秒单位）
                network_disabled=network_disabled,  # ⚠️ 禁用网络
                environment={"PYTHONUNBUFFERED": "1"},  # Python 输出不缓冲
            )

            # ——— 轮询等待容器结束 ———
            # 不用 container.wait(timeout=T) 一把梭，而是短间隔轮询，
            # 每次轮询间隙检查 cancel_check() 回调——这样 RUNNING 任务也能被取消。
            #
            # 坑：Windows 命名管道上抛 ConnectionError，TCP 上抛 ReadTimeout，
            # 两种都要捕获，否则超时会被当成普通异常导致状态错误。
            POLL_INTERVAL = 0.5  # 每 0.5 秒检查一次
            deadline = time.monotonic() + timeout

            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    # ——— 超时 ———
                    logger.warning("Task timed out after %ss, killing container", timeout)
                    try:
                        container.kill()  # SIGKILL 强杀
                    except docker.errors.APIError:
                        pass  # 容器可能已经自行退出了
                    wait_result = container.wait()  # 等它确认死亡
                    return SandboxResult(
                        exit_code=wait_result.get("StatusCode", -1),
                        output=self._get_logs(container),
                        timed_out=True,
                        duration=time.monotonic() - start,
                    )

                try:
                    wait_result = container.wait(timeout=min(POLL_INTERVAL, remaining))
                    break  # 容器正常结束，退出轮询
                except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError):
                    # wait 超时 = 容器还在跑
                    # 检查用户是否请求了取消
                    if cancel_check is not None and cancel_check():
                        logger.warning("Task cancelled by user, killing container")
                        try:
                            container.kill()  # SIGKILL 强杀
                        except docker.errors.APIError:
                            pass  # 容器可能已经自行退出了
                        wait_result = container.wait()  # 等它确认死亡
                        return SandboxResult(
                            exit_code=wait_result.get("StatusCode", -1),
                            output=self._get_logs(container),
                            cancelled=True,
                            duration=time.monotonic() - start,
                        )
                    # 没取消，继续下一轮轮询

            # ——— 正常结束 ———
            exit_code = wait_result.get("StatusCode", -1)
            output = self._get_logs(container)

            return SandboxResult(
                exit_code=exit_code,
                output=output,
                oom=exit_code == OOM_EXIT_CODE,  # 退出码 137 = OOM killed
                duration=time.monotonic() - start,
            )

        except docker.errors.ImageNotFound:
            # 镜像不存在（ensure_image 拉取失败）
            return SandboxResult(
                error="沙箱镜像不存在", exit_code=-1, duration=time.monotonic() - start
            )
        except docker.errors.APIError as exc:
            # Docker daemon 返回错误（比如磁盘满了、权限不够）
            logger.error("Docker API error: %s", exc)
            return SandboxResult(
                error=f"Docker API 错误: {exc}", exit_code=-1, duration=time.monotonic() - start
            )
        finally:
            # ——— 无论成功失败，都要销毁容器 ———
            if container is not None:
                try:
                    container.remove(force=True)  # force=True = 容器还在跑也强制删
                except docker.errors.APIError:
                    logger.exception("Failed to remove container %s", container.id)

    @staticmethod
    def _get_logs(container):
        """同时取 stdout 和 stderr，合并返回。
        用户代码的 print() 输出就是靠这个拿到的。
        """
        try:
            logs = container.logs(stdout=True, stderr=True)
            return logs.decode("utf-8", errors="replace")
        except docker.errors.APIError:
            logger.exception("Failed to read logs from container %s", container.id)
            return ""
