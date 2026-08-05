"""任务日志的 Elasticsearch 索引与检索。

写入/查询失败一律降级为日志记录，绝不影响任务主流程——
ES 是辅助系统，不是任务执行的关键路径。
"""

import logging

from django.conf import settings
from django.utils import timezone
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

INDEX_MAPPING = {
    "settings": {
        "number_of_shards": 1,
        "number_of_replicas": 0,
    },
    "mappings": {
        "properties": {
            "task_id": {"type": "keyword"},
            "task_name": {"type": "keyword"},
            "owner_id": {"type": "integer"},
            "worker_id": {"type": "keyword"},
            "status": {"type": "keyword"},
            "log_type": {"type": "keyword"},  # run / error
            "output": {"type": "text"},
            "error": {"type": "text"},
            "duration": {"type": "float"},
            "created_at": {"type": "date"},
        },
    },
}


def get_client():
    return Elasticsearch(settings.ELASTICSEARCH_URL)


def ensure_index():
    """索引不存在则创建（幂等）。"""
    index = settings.ELASTICSEARCH_INDEX
    es = get_client()
    if not es.indices.exists(index=index):
        es.indices.create(index=index, body=INDEX_MAPPING)
        logger.info("Created ES index %s", index)


def index_task_log(task):
    """把一次任务执行的结果写入 ES。失败不影响任务本身。"""
    try:
        ensure_index()
        result = task.result if isinstance(task.result, dict) else {}
        doc = {
            "task_id": str(task.id),
            "task_name": task.name,
            "owner_id": task.owner_id,
            "worker_id": task.worker_id,
            "status": task.status,
            "log_type": "error" if task.error_message else "run",
            "output": result.get("output", ""),
            "error": task.error_message,
            "duration": task.duration or 0,
            "created_at": timezone.now().isoformat(),
        }
        get_client().index(index=settings.ELASTICSEARCH_INDEX, document=doc)
    except Exception:
        logger.exception("Failed to index task log to ES for task %s", task.id)


def search_logs(q=None, task_id=None, owner_id=None, status=None, size=50):
    """按关键词/任务/用户/状态检索日志，按时间倒序。"""
    must = []
    if q:
        must.append({"multi_match": {"query": q, "fields": ["output", "error", "task_name"]}})
    if task_id:
        must.append({"term": {"task_id": task_id}})
    if owner_id:
        must.append({"term": {"owner_id": owner_id}})
    if status:
        must.append({"term": {"status": status}})

    body = {
        "query": {"bool": {"must": must}} if must else {"match_all": {}},
        "size": size,
        "sort": [{"created_at": "desc"}],
    }
    resp = get_client().search(index=settings.ELASTICSEARCH_INDEX, body=body)
    return [_source(h) for h in resp["hits"]["hits"]]


def _source(hit):
    src = dict(hit["_source"])
    src["_id"] = hit["_id"]
    src["_score"] = hit.get("_score")
    return src
