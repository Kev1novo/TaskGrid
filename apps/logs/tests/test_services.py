import pytest

from apps.logs import services
from apps.tasks.models import Task

pytestmark = pytest.mark.django_db


def test_ensure_index_creates_when_missing(fake_es):
    fake_es.indices.exists.return_value = False
    services.ensure_index()
    fake_es.indices.create.assert_called_once()


def test_ensure_index_skips_when_exists(fake_es):
    fake_es.indices.exists.return_value = True
    services.ensure_index()
    fake_es.indices.create.assert_not_called()


def test_index_task_log_doc_fields(fake_es, user):
    task = Task.objects.create(
        name="t",
        owner=user,
        code="print(1)",
        status=Task.Status.SUCCESS,
        worker_id="w1",
    )
    task.result = {"output": "ok"}
    task.save()
    services.index_task_log(task)
    doc = fake_es.index.call_args.kwargs["document"]
    assert doc["task_id"] == str(task.id)
    assert doc["status"] == "success"
    assert doc["log_type"] == "run"
    assert doc["output"] == "ok"


def test_index_task_log_error_type(fake_es, user):
    task = Task.objects.create(
        name="t",
        owner=user,
        code="print(1)",
        status=Task.Status.FAILED,
        error_message="boom",
    )
    services.index_task_log(task)
    doc = fake_es.index.call_args.kwargs["document"]
    assert doc["log_type"] == "error"
    assert doc["error"] == "boom"


def test_index_task_log_degrades_on_error(fake_es, user):
    fake_es.indices.exists.side_effect = Exception("es down")
    task = Task.objects.create(name="t", owner=user, code="print(1)")
    # 降级设计：ES 失败不应抛异常影响主流程
    services.index_task_log(task)


def test_search_logs_builds_filters(fake_es):
    fake_es.search.return_value = {
        "hits": {"hits": [{"_source": {"output": "hello"}, "_id": "abc", "_score": 1.0}]}
    }
    hits = services.search_logs(q="hello", owner_id=1, status="success")
    assert len(hits) == 1
    assert hits[0]["_id"] == "abc"
    body = fake_es.search.call_args.kwargs["body"]
    must = body["query"]["bool"]["must"]
    assert any("multi_match" in m for m in must)
    assert {"term": {"owner_id": 1}} in must
    assert {"term": {"status": "success"}} in must
