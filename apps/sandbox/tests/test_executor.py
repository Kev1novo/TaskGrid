from unittest.mock import MagicMock

import requests

import docker
from apps.sandbox.executor import SandboxExecutor, SandboxResult


def _container(wait_results=None, logs="", wait_error=None):
    container = MagicMock()
    if wait_error is not None:
        container.wait.side_effect = wait_error
    else:
        container.wait.side_effect = wait_results or [{"StatusCode": 0}]
    container.logs.return_value = logs.encode("utf-8")
    return container


def _client(container=None, images_ok=True, run_error=None):
    client = MagicMock()
    if run_error is not None:
        client.containers.run.side_effect = run_error
    else:
        client.containers.run.return_value = container
    if images_ok:
        client.images.get.return_value = MagicMock()
    else:
        # ensure_image 里 get 抛 ImageNotFound 会转去 pull，pull 再失败才报错
        client.images.get.side_effect = docker.errors.ImageNotFound("no local image")
        client.images.pull.side_effect = docker.errors.ImageNotFound("no remote image")
    return client


def test_success():
    container = _container(wait_results=[{"StatusCode": 0}], logs="ok")
    result = SandboxExecutor(client=_client(container)).execute(code="print(1)")
    assert result.success is True
    assert result.output == "ok"
    assert result.oom is False
    assert result.timed_out is False


def test_failed_exit_code():
    container = _container(wait_results=[{"StatusCode": 1}], logs="boom")
    result = SandboxExecutor(client=_client(container)).execute(code="x")
    assert result.success is False
    assert result.output == "boom"


def test_oom_detected():
    container = _container(wait_results=[{"StatusCode": 137}])
    result = SandboxExecutor(client=_client(container)).execute(code="x")
    assert result.oom is True


def test_timeout_kills_container():
    """超时：executor 轮询直到 deadline 到期，强杀容器并返回 timed_out=True"""
    container = MagicMock()

    def _wait(timeout=None):
        # kill 之前一直抛 ReadTimeout（模拟容器还在跑），kill 之后返回退出码
        if container.kill.called:
            return {"StatusCode": -1}
        raise requests.exceptions.ReadTimeout()

    container.wait.side_effect = _wait
    container.logs.return_value = b""

    result = SandboxExecutor(client=_client(container)).execute(code="x", timeout=0.1)
    assert result.timed_out is True
    container.kill.assert_called_once()


def test_image_missing_returns_error():
    result = SandboxExecutor(client=_client(images_ok=False)).execute(code="x")
    assert result.exit_code == -1
    assert "镜像" in result.error


def test_docker_api_error_returns_error():
    client = _client(run_error=docker.errors.APIError("daemon down"))
    result = SandboxExecutor(client=client).execute(code="x")
    assert result.exit_code == -1
    assert "Docker API" in result.error


def test_sandbox_result_success_property():
    assert SandboxResult(exit_code=0).success is True
    assert SandboxResult(exit_code=1).success is False


def test_cancel_kills_container():
    """取消：cancel_check 返回 True 时强杀容器，返回 cancelled=True"""
    container = MagicMock()

    def _wait(timeout=None):
        if container.kill.called:
            return {"StatusCode": -1}
        raise requests.exceptions.ReadTimeout()

    container.wait.side_effect = _wait
    container.logs.return_value = b"cancelled output"

    result = SandboxExecutor(client=_client(container)).execute(code="x", cancel_check=lambda: True)
    assert result.cancelled is True
    assert "cancelled output" in result.output
    container.kill.assert_called_once()
