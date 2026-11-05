"""Rows as this service sees them: `catalog` is another process, so types are copies."""

import uuid

import factory
from django.utils import timezone

from .auth import Owner
from .models import (
    BatteryTypeRef,
    BatteryTypeRefSlot,
    Questionnaire,
    QuestionnaireTypeRef,
)


def make_owner() -> Owner:
    return Owner(pk=uuid.uuid4())


class TypeRefFactory(factory.django.DjangoModelFactory):
    class Meta:
        abstract = True
        exclude = ("owner",)

    owner = factory.LazyFunction(make_owner)
    id = factory.LazyFunction(uuid.uuid4)
    owner_id = factory.LazyAttribute(lambda row: row.owner.pk)
    created_at = factory.LazyFunction(timezone.now)
    updated_at = factory.LazyFunction(timezone.now)


class QuestionnaireTypeFactory(TypeRefFactory):
    class Meta:
        model = QuestionnaireTypeRef

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


class BatteryTypeFactory(TypeRefFactory):
    class Meta:
        model = BatteryTypeRef
        skip_postgeneration_save = True

    title = factory.Sequence(lambda n: f"Battery {n}")

    @factory.post_generation
    def questionnaire_types(self, create, extracted, **kwargs):  # noqa: ARG002
        for order, qt in enumerate(extracted or []):
            BatteryTypeRefSlot.objects.create(
                battery_type=self, questionnaire_type_id=qt.pk, order=order
            )


class QuestionnaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Questionnaire

    questionnaire_type = factory.SubFactory(QuestionnaireTypeFactory)
    owner_id = factory.SelfAttribute("questionnaire_type.owner_id")
