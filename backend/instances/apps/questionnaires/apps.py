from django.apps import AppConfig


class QuestionnairesConfig(AppConfig):
    name = "apps.questionnaires"
    label = "questionnaires"
    # Every model has a UUID key. Pinned anyway, so a new model without one gets the
    # same migration on both engines, and MongoDB's system check flags it (#29).
    default_auto_field = "django.db.models.BigAutoField"
