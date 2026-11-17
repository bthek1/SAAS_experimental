from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("instances-admin/", admin.site.urls),
    path("api/", include("apps.questionnaires.urls")),
    path("internal/", include("apps.questionnaires.internal_urls")),
]
