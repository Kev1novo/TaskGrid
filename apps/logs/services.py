"""任务日志的 Elasticsearch 索引与检索。

写入/查询失败一律降级为日志记录，绝不影响任务主流程——
ES 是辅助系统，不是任务执行的关键路径。
"""

import logging

from django.conf import settings
from django.utils import timezone
from elasticsearch import Elasticsearch

logger = logging.getLogger(__name__)

# ——————————————————————————————————————————————————————
# ES 索引结构定义（类似建表语句）
# keyword 类型 → 精确匹配（用于过滤：task_id、status、owner_id）
# text 类型    → 全文检索（用于搜索：output、error）
# ——————————————————————————————————————————————————————
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
            "log_type": {"type": "keyword"},  # "run"=正常执行 / "error"=有错误
            "output": {"type": "text"},  # 代码执行输出 → 可以被全文搜索
            "error": {"type": "text"},  # 错误信息 → 可以被全文搜索
            "duration": {"type": "float"},
            "created_at": {"type": "date"},
        },
    },
}


_es_client = None  # 模块级单例，避免每个请求都创建新连接


def get_client():
    """获取 ES 客户端连接（惰性初始化，模块级单例）。"""
    global _es_client
    if _es_client is None:
        _es_client = Elasticsearch(settings.ELASTICSEARCH_URL)
    return _es_client


def ensure_index():
    """索引不存在则创建（幂等——第二次调用不做任何事）。"""
    index = settings.ELASTICSEARCH_INDEX
    es = get_client()
    if not es.indices.exists(index=index):
        es.indices.create(index=index, body=INDEX_MAPPING)
        logger.info("Created ES index %s", index)


def index_task_log(task):
    """把一次任务执行的结果写入 ES 索引，供后续检索。
    ⚠️ 降级设计：写入失败只记日志，绝不影响任务主流程。
    """
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
        # 只记日志，不抛异常——ES 挂了任务照常完成
        logger.exception("Failed to index task log to ES for task %s", task.id)


def search_logs(q=None, task_id=None, owner_id=None, status=None, size=50):
    """按关键词/任务/用户/状态检索日志，按时间倒序。

    参数：
      q        全文关键词（匹配 output、error、task_name）
      task_id  精确查某个任务的所有日志
      owner_id 按创建者过滤（权限隔离的关键——用户只能搜自己的）
      status   按任务状态过滤（如只搜失败的）
      size     返回条数上限

    返回格式：
      [{...fields..., "_id": "es_doc_id", "_score": 2.5}, ...]

    ⚠️ 降级设计：ES 异常时返回空列表，绝不抛异常——
    与 index_task_log 保持一致的降级行为。
    """
    try:
        # 构建 ES 的 bool 查询条件
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
            "sort": [{"created_at": "desc"}],  # 最新的排前面
        }

        # 调用 ES 搜索
        resp = get_client().search(index=settings.ELASTICSEARCH_INDEX, body=body)
        return [_source(h) for h in resp["hits"]["hits"]]
    except Exception:
        logger.exception("Failed to search logs in ES")
        return []


def _source(hit):
    """把 ES 返回的原始结果整理成字典，附加 _id 和 _score。"""
    src = dict(hit["_source"])
    src["_id"] = hit["_id"]  # 文档 ID
    src["_score"] = hit.get("_score")  # 相关度分数（全文搜索才有意义）
    return src


def delete_task_logs(task_ids):
    """批量删除指定任务的 ES 日志（降级设计：失败只记日志）。"""
    if not task_ids:
        return
    try:
        get_client().delete_by_query(
            index=settings.ELASTICSEARCH_INDEX,
            body={"query": {"terms": {"task_id": [str(tid) for tid in task_ids]}}},
        )
    except Exception:
        logger.exception("Failed to delete ES logs for %d tasks", len(task_ids))
