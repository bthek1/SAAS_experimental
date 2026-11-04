import factory

from apps.catalog import factories as catalog_factories
from apps.catalog.events import snapshot
from apps.catalog.factories import UserFactory
from apps.catalog.models import BatteryType, BatteryTypeItem

from . import refs
from .models import BatteryTypeRef, Questionnaire, QuestionnaireTypeRef

__all__ = [
    "BatteryTypeFactory",
    "QuestionnaireFactory",
    "QuestionnaireTypeFactory",
    "UserFactory",
]


def _copy(source, model):
    refs.store_snapshot(snapshot(source))
    return model.objects.get(pk=source.pk)


class QuestionnaireTypeFactory(catalog_factories.QuestionnaireTypeFactory):
    """Creates the catalog row and returns its copy, as a settled system would have."""

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        source = super()._create(model_class, *args, **kwargs)
        return _copy(source, QuestionnaireTypeRef)


class BatteryTypeFactory(catalog_factories.BatteryTypeFactory):
    class Meta:
        skip_postgeneration_save = True

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        source = super()._create(model_class, *args, **kwargs)
        return _copy(source, BatteryTypeRef)

    @factory.post_generation
    def questionnaire_types(self, create, extracted, **kwargs):  # noqa: ARG002
        for order, qt in enumerate(extracted or []):
            BatteryTypeItem.objects.create(
                battery_type_id=self.pk, questionnaire_type_id=qt.pk, order=order
            )
        # Store the slots. The version has not moved, so _upsert alone would skip them.
        source = BatteryType.objects.get(pk=self.pk)
        BatteryTypeRef.objects.filter(pk=self.pk).delete()
        refs.store_snapshot(snapshot(source))


class QuestionnaireFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Questionnaire

    questionnaire_type = factory.SubFactory(QuestionnaireTypeFactory)
    owner = factory.SelfAttribute("questionnaire_type.owner")
