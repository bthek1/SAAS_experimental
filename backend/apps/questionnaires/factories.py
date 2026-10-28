import factory
from django.contrib.auth import get_user_model

from .models import BatteryType, BatteryTypeItem, Questionnaire, QuestionnaireType


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = get_user_model()

    email = factory.Sequence(lambda n: f"user{n}@example.com")
    password = factory.django.Password("pass1234")


class QuestionnaireTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = QuestionnaireType

    owner = factory.SubFactory(UserFactory)
    title = factory.Sequence(lambda n: f"Questionnaire {n}")
    questionnaire_json = factory.LazyFunction(
        lambda: {
            "pages": [
                {
                    "name": "page1",
                    "elements": [{"type": "text", "name": "q1", "title": "Q1"}],
                }
            ]
        }
    )


class BatteryTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = BatteryType

    owner = factory.SubFactory(UserFactory)
    title = factory.Sequence(lambda n: f"Battery {n}")

    @factory.post_generation
    def questionnaire_types(self, create, extracted, **kwargs):  # noqa: ARG002
        for order, qt in enumerate(extracted or []):
            BatteryTypeItem.objects.create(
                battery_type=self, questionnaire_type=qt, order=order
            )


class QuestionnaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Questionnaire

    questionnaire_type = factory.SubFactory(QuestionnaireTypeFactory)
    owner = factory.SelfAttribute("questionnaire_type.owner")
