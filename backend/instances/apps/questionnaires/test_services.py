import pytest
from freezegun import freeze_time

from . import services
from .factories import QuestionnaireFactory


@pytest.mark.django_db
class TestSubmitQuestionnaire:
    @freeze_time("2026-01-02 03:04:05")
    def test_saves_answers_metrics_and_snapshot(self, qtype):
        q = QuestionnaireFactory(questionnaire_type=qtype)
        result = services.submit_questionnaire(q, {"q1": "hi"}, {"total": 3})
        assert result.answers_json == {"q1": "hi"}
        assert result.metrics_json == {"total": 3}
        assert result.questionnaire_json_snapshot == qtype.questionnaire_json
        assert result.submitted_at.isoformat() == "2026-01-02T03:04:05+00:00"

    def test_second_submit_raises(self, qtype):
        q = QuestionnaireFactory(questionnaire_type=qtype)
        services.submit_questionnaire(q, {}, {})
        with pytest.raises(services.AlreadySubmitted):
            services.submit_questionnaire(q, {"q1": "again"}, {})
        q.refresh_from_db()
        assert q.answers_json == {}

    def test_snapshot_survives_type_edit(self, qtype):
        q = QuestionnaireFactory(questionnaire_type=qtype)
        original = qtype.questionnaire_json
        services.submit_questionnaire(q, {}, {})
        qtype.questionnaire_json = {"pages": []}
        qtype.save()
        q.refresh_from_db()
        assert q.questionnaire_json_snapshot == original
