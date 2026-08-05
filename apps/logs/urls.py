from django.urls import path

from .views import LogSearchView

urlpatterns = [
    path("search/", LogSearchView.as_view(), name="log_search"),
]
