import uuid

import pytest
from django.db.models import RestrictedError

from . import services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from .models import Battery, BatteryType, Questionnaire, QuestionnaireType


@pytest.mark.django_db
class TestQuestionnaireType:
    def test_id_is_uuid(self, qtype):
        assert isinstance(qtype.id, uuid.UUID)

    def test_str_is_title(self, qtype):
        assert str(qtype) == qtype.title

    def test_ordering_newest_first(self, user):
        first = QuestionnaireTypeFactory(owner=user)
        second = QuestionnaireTypeFactory(owner=user)
        assert list(QuestionnaireType.objects.all()) == [second, first]


@pytest.mark.django_db
class TestQuestionnaire:
    def test_defaults(self, qtype):
        q = QuestionnaireFactory(questionnaire_type=qtype)
        assert q.answers_json == {}
        assert q.metrics_json == {}
        assert q.questionnaire_json_snapshot == {}
        assert q.submitted_at is None
        assert q.owner == qtype.owner

    def test_share_tokens_are_unique(self, qtype):
        a = QuestionnaireFactory(questionnaire_type=qtype)
        b = QuestionnaireFactory(questionnaire_type=qtype)
        assert a.share_token != b.share_token

    def test_str_includes_type_title_and_name(self, qtype):
        q = QuestionnaireFactory(questionnaire_type=qtype, name="Alice")
        assert str(q) == f"{qtype.title} - Alice"

    def test_str_falls_back_to_token(self, qtype):
        q = QuestionnaireFactory(questionnaire_type=qtype)
        assert str(q.share_token) in str(q)

    def test_type_with_instances_cannot_be_deleted(self, qtype):
        QuestionnaireFactory(questionnaire_type=qtype)
        with pytest.raises(RestrictedError):
            qtype.delete()


@pytest.mark.django_db
class TestBattery:
    def test_create_battery_creates_questionnaires_in_order(self, user):
        qt1, qt2 = (
            QuestionnaireTypeFactory(owner=user),
            QuestionnaireTypeFactory(owner=user),
        )
        bt = BatteryTypeFactory(owner=user, questionnaire_types=[qt2, qt1])
        battery = services.create_battery(bt, "Run 1")
        slots = list(battery.questionnaires.order_by("battery_order"))
        assert [s.questionnaire_type for s in slots] == [qt2, qt1]
        assert [s.battery_order for s in slots] == [0, 1]
        assert all(s.owner == user for s in slots)
        assert battery.owner == user
        assert battery.name == "Run 1"

    def test_create_battery_with_no_types(self, user):
        battery = services.create_battery(BatteryTypeFactory(owner=user))
        assert battery.questionnaires.count() == 0

    def test_deleting_battery_keeps_responses(self, user, qtype):
        battery = services.create_battery(
            BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
        )
        q = battery.questionnaires.get()
        battery.delete()
        q.refresh_from_db()
        assert q.battery is None

    def test_type_in_battery_type_cannot_be_deleted(self, user, qtype):
        BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
        with pytest.raises(RestrictedError):
            qtype.delete()

    def test_str(self, user):
        bt = BatteryTypeFactory(owner=user, title="Intake")
        assert str(services.create_battery(bt, "Bob")) == "Intake - Bob"


@pytest.mark.django_db
def test_deleting_owner_cascades_everything(user, qtype):
    bt = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    services.create_battery(bt)
    QuestionnaireFactory(questionnaire_type=qtype)
    user.delete()
    assert not QuestionnaireType.objects.exists()
    assert not BatteryType.objects.exists()
    assert not Battery.objects.exists()
    assert not Questionnaire.objects.exists()
