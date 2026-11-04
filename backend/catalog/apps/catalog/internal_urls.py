from django.urls import path

from .internal_views import HealthView, TypeSnapshotListView, TypeSnapshotView

KINDS = {"questionnaire-types": "questionnaire_type", "battery-types": "battery_type"}

urlpatterns = [
    path("health/", HealthView.as_view()),
    *[
        route
        for slug, kind in KINDS.items()
        for route in (
            path(f"{slug}/", TypeSnapshotListView.as_view(kind=kind)),
            path(f"{slug}/<uuid:type_id>/", TypeSnapshotView.as_view(kind=kind)),
        )
    ],
]
