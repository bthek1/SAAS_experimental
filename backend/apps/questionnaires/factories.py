import factory

from apps.catalog.factories import (
    BatteryTypeFactory,
    QuestionnaireTypeFactory,
    UserFactory,
)

from .models import Questionnaire

__all__ = [
    "BatteryTypeFactory",
    "QuestionnaireFactory",
    "QuestionnaireTypeFactory",
    "UserFactory",
]


class QuestionnaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Questionnaire

    questionnaire_type = factory.SubFactory(QuestionnaireTypeFactory)
    owner = factory.SelfAttribute("questionnaire_type.owner")
