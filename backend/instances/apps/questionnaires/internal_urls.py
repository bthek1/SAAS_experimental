from django.urls import path

from .internal_views import EventView, HealthView, RetireView

urlpatterns = [
    path("health/", HealthView.as_view()),
    path("events/", EventView.as_view()),
    path("refs/<str:kind>/<uuid:ref_id>/retire/", RetireView.as_view()),
]
