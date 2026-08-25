"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def api_root(request):
    return JsonResponse(
        {
            "name": "TaskGrid API",
            "version": "v1",
            "endpoints": {
                "admin": "/admin/",
                "auth": "/api/v1/auth/",
            },
        }
    )


def health(request):
    """健康检查：验证 DB / Redis / Docker 连通性，k8s/docker-compose 探活用。"""
    import redis
    from django.conf import settings
    from django.db import connections

    import docker

    checks = {}
    errors = 0

    # ——— 数据库 ———
    try:
        connections["default"].cursor()
        checks["db"] = "ok"
    except Exception as e:
        checks["db"] = f"error: {e}"
        errors += 1

    # ——— Redis ———
    try:
        r = redis.Redis.from_url(settings.CELERY_BROKER_URL)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        checks["redis"] = f"error: {e}"
        errors += 1

    # ——— Docker（仅 worker 容器有 docker.sock，web 上失败是正常的） ———
    try:
        client = docker.from_env()
        client.ping()
        checks["docker"] = "ok"
    except Exception as e:
        checks["docker"] = f"unavailable: {e}"

    return JsonResponse(checks, status=500 if errors else 200)


urlpatterns = [
    path("", api_root, name="api_root"),
    path("health/", health, name="health"),
    path("admin/", admin.site.urls),
    path("api/v1/auth/", include("apps.users.urls")),
    path("api/v1/tasks/", include("apps.tasks.urls")),
    path("api/v1/nodes/", include("apps.nodes.urls")),
    path("api/v1/logs/", include("apps.logs.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
