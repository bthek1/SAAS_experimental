import pytest
from django.test import override_settings
from freezegun import freeze_time

from . import services, views
from .factories import QuestionnaireFactory, QuestionnaireTypeFactory
from .pdf import render_response_html, resolve_metrics, resolve_questions

SURVEY = {
    "pages": [
        {
            "name": "p1",
            "elements": [
                {"type": "text", "name": "q1", "title": "Your name"},
                {
                    "type": "radiogroup",
                    "name": "color",
                    "title": "Colour",
                    "choices": [{"value": "r", "text": "Red"}, "blue"],
                },
                {"type": "checkbox", "name": "pets", "choices": ["cat", "dog"]},
                {"type": "boolean", "name": "ok", "title": "OK?"},
                {
                    "type": "panel",
                    "name": "panel1",
                    "elements": [{"type": "comment", "name": "note", "title": "Note"}],
                },
                {
                    "type": "matrix",
                    "name": "grid",
                    "title": "Grid",
                    "columns": [
                        {"value": 1, "text": "Low"},
                        {"value": 2, "text": "High"},
                    ],
                    "rows": [{"value": "a", "text": "Row A"}, "b"],
                },
                {"type": "html", "name": "intro", "html": "<p>hi</p>"},
            ],
        }
    ],
    "calculatedValues": [
        {"name": "total_score", "expression": "1"},
        {"name": "risk", "title": "Risk level", "expression": "2"},
    ],
}

ANSWERS = {
    "q1": "Pat",
    "color": "r",
    "pets": ["cat", "dog"],
    "ok": True,
    "note": "Fine",
    "grid": {"a": 2},
}


def pdf_url(pk):
    return f"/api/questionnaires/{pk}/pdf/"


@pytest.fixture
def submitted(user):
    qtype = QuestionnaireTypeFactory(
        owner=user, title="Check in / weekly", questionnaire_json=SURVEY
    )
    q = QuestionnaireFactory(questionnaire_type=qtype, name="Pat")
    return services.submit_questionnaire(q, ANSWERS, {"total_score": 7, "risk": "low"})


class TestResolveQuestions:
    def test_labels_flattening_and_skips(self):
        questions = resolve_questions(SURVEY, ANSWERS)
        by_title = {q["title"]: q for q in questions}
        assert list(by_title) == ["Your name", "Colour", "pets", "OK?", "Note", "Grid"]
        assert by_title["Colour"]["display_value"] == "Red"
        assert by_title["pets"]["display_value"] == "cat, dog"
        assert by_title["OK?"]["display_value"] == "Yes"
        assert by_title["Note"]["display_value"] == "Fine"
        assert by_title["Grid"]["columns"] == ["Low", "High"]
        assert by_title["Grid"]["rows"] == [
            {"label": "Row A", "selected": "High"},
            {"label": "b", "selected": None},
        ]

    def test_missing_answers_are_empty(self):
        questions = resolve_questions(SURVEY, {})
        assert questions[0]["display_value"] == ""

    def test_tolerates_malformed_definitions(self):
        assert resolve_questions({"pages": [None, {"elements": [None, "x"]}]}, {}) == []


def test_resolve_metrics_uses_titles_and_order():
    assert resolve_metrics(SURVEY, {"risk": "low", "total_score": 7, "other": 1}) == [
        {"label": "Total Score", "value": 7},
        {"label": "Risk level", "value": "low"},
    ]


@pytest.mark.django_db
class TestTemplate:
    def test_renders_title_answers_metrics(self, submitted):
        html = render_response_html(submitted)
        assert "Check in / weekly" in html
        assert "Pat" in html
        assert "Red" in html
        assert "Risk level" in html
        assert "No answer" not in html

    def test_renders_from_snapshot_not_live_type(self, submitted):
        submitted.questionnaire_type.questionnaire_json = {"pages": []}
        submitted.questionnaire_type.save()
        submitted.refresh_from_db()
        assert "Your name" in render_response_html(submitted)

    def test_escapes_answers(self, user):
        qtype = QuestionnaireTypeFactory(owner=user, questionnaire_json=SURVEY)
        q = services.submit_questionnaire(
            QuestionnaireFactory(questionnaire_type=qtype),
            {"q1": "<script>x</script>"},
            {},
        )
        html = render_response_html(q)
        assert "<script>x</script>" not in html
        assert "&lt;script&gt;" in html


@pytest.mark.django_db
class TestPdfEndpoint:
    @freeze_time("2026-03-04 10:00:00")
    def test_returns_pdf_download(self, auth_client, submitted):
        response = auth_client.get(pdf_url(submitted.id))
        assert response.status_code == 200
        assert response["Content-Type"] == "application/pdf"
        assert response.content.startswith(b"%PDF")
        assert response["Content-Disposition"] == (
            'attachment; filename="Check-in-weekly-2026-03-04.pdf"'
        )

    def test_accept_pdf_header_is_honoured(self, auth_client, submitted):
        response = auth_client.get(pdf_url(submitted.id), HTTP_ACCEPT="application/pdf")
        assert response.status_code == 200
        assert response.content.startswith(b"%PDF")

    def test_pdf_requires_auth(self, api_client, submitted):
        assert api_client.get(pdf_url(submitted.id)).status_code == 401

    def test_pdf_requires_owner(self, other_client, submitted):
        assert other_client.get(pdf_url(submitted.id)).status_code == 404

    def test_pdf_unsubmitted_400(self, auth_client, qtype):
        q = QuestionnaireFactory(questionnaire_type=qtype)
        response = auth_client.get(pdf_url(q.id))
        assert response.status_code == 400
        assert "not been submitted" in response.json()["detail"]


@pytest.mark.django_db
@override_settings(CORS_ALLOWED_ORIGINS=["http://localhost:5174"])
def test_pdf_filename_is_readable_cross_origin(auth_client, submitted):
    # Without this header the browser hides Content-Disposition from the SPA.
    response = auth_client.get(
        pdf_url(submitted.id), HTTP_ORIGIN="http://localhost:5174"
    )
    assert "content-disposition" in response["Access-Control-Expose-Headers"].lower()


# ── Caching (#11) ─────────────────────────────────────────────────────────────


@pytest.fixture
def render(mocker):
    """Counts renders. Each returns different bytes, so a stale PDF shows."""
    calls = iter(range(1000))
    return mocker.patch(
        "apps.questionnaires.views.generate_response_pdf",
        side_effect=lambda _instance: b"%%PDF-%d" % next(calls),
    )


@pytest.mark.usefixtures("cache_on")
class TestPdfCache:
    def test_second_download_does_not_render(self, auth_client, submitted, render):
        first = auth_client.get(pdf_url(submitted.id))
        second = auth_client.get(pdf_url(submitted.id))
        assert first.status_code == second.status_code == 200
        assert second.content == first.content
        assert second["Content-Type"] == "application/pdf"
        assert render.call_count == 1

    def test_rename_renders_again(self, auth_client, submitted, render):
        before = auth_client.get(pdf_url(submitted.id)).content
        response = auth_client.patch(
            f"/api/questionnaires/{submitted.id}/", {"name": "Sam"}, format="json"
        )
        assert response.status_code == 200
        assert auth_client.get(pdf_url(submitted.id)).content != before
        assert render.call_args.args[0].name == "Sam"

    def test_type_title_change_renders_again(self, auth_client, submitted, render):
        before = auth_client.get(pdf_url(submitted.id)).content
        auth_client.patch(
            f"/api/questionnaire-types/{submitted.questionnaire_type_id}/",
            {"title": "Retitled"},
            format="json",
        )
        assert auth_client.get(pdf_url(submitted.id)).content != before
        assert render.call_args.args[0].questionnaire_type.title == "Retitled"

    def test_other_owner_gets_404_with_a_cached_pdf(
        self, auth_client, other_client, submitted, render
    ):
        assert auth_client.get(pdf_url(submitted.id)).status_code == 200
        assert other_client.get(pdf_url(submitted.id)).status_code == 404
        assert render.call_count == 1

    def test_unsubmitted_is_still_400(self, auth_client, qtype, render):
        draft = QuestionnaireFactory(questionnaire_type=qtype)
        assert auth_client.get(pdf_url(draft.id)).status_code == 400
        assert render.call_count == 0

    def test_filename_date_is_fresh_on_a_hit(self, auth_client, submitted, render):
        with freeze_time("2026-11-03 12:00:00"):
            first = auth_client.get(pdf_url(submitted.id))
        with freeze_time("2026-11-04 00:30:00"):
            second = auth_client.get(pdf_url(submitted.id))
        assert render.call_count == 1
        assert "2026-11-03.pdf" in first["Content-Disposition"]
        assert "2026-11-04.pdf" in second["Content-Disposition"]

    def test_oversized_pdf_is_not_stored(self, auth_client, submitted, mocker):
        oversized = b"x" * (views.PDF_CACHE_MAX_BYTES + 1)
        render = mocker.patch(
            "apps.questionnaires.views.generate_response_pdf", return_value=oversized
        )
        auth_client.get(pdf_url(submitted.id))
        response = auth_client.get(pdf_url(submitted.id))
        assert response.content == oversized
        assert render.call_count == 2

    def test_a_generation_bump_keeps_the_pdf(self, auth_client, submitted, render):
        # Content-addressed: deleting another row should not cost a re-render.
        other = QuestionnaireFactory(questionnaire_type=submitted.questionnaire_type)
        auth_client.get(pdf_url(submitted.id))
        auth_client.delete(f"/api/questionnaires/{other.id}/")
        auth_client.get(pdf_url(submitted.id))
        assert render.call_count == 1
