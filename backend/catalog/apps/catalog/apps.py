from django.apps import AppConfig


class CatalogConfig(AppConfig):
    name = "apps.catalog"
    label = "catalog"

    def ready(self):
        from . import user_events

        user_events.connect()
