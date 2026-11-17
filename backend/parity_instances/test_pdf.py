"""A submitted response as a PDF: what the owner downloads from the SPA.

Layout and bytes are free (the .NET version draws its own, #43). What is pinned is
the response around the file and the text in it: the questions, the answers by their
display labels, and the scores.
"""

import io
import re
from datetime import UTC, datetime

import pytest
from pypdf import PdfReader

from .support import as_event, create_questionnaire, qtype_snapshot, submit

SPA_ORIGIN = "http://localhost:5174"
SURVEY = {
    "pages": [
        {
            "name": "p1",
            "elements": [
                {"type": "text", "name": "nickname", "title": "Your nickname"},
                {
                    "type": "radiogroup",
                    "name": "fruit",
                    "title": "Favourite fruit",
                    "choices": [
                        {"value": "a", "text": "Apple"},
                        {"value": "b", "text": "Banana"},
                    ],
                },
                {
                    "type": "checkbox",
                    "name": "colours",
                    "title": "Colours you like",
                    "choices": ["Red", {"value": "g", "text": "Green"}],
                },
                {"type": "boolean", "name": "agree", "title": "Do you agree"},
                {"type": "html", "name": "intro", "html": "<p>Hidden html block</p>"},
                {
                    "type": "panel",
                    "name": "panel",
                    "elements": [{"type": "comment", "name": "notes_in_panel"}],
                },
                {"type": "text", "name": "skipped", "title": "Left blank"},
                {
                    "type": "matrix",
                    "name": "mood",
                    "title": "Mood grid",
                    "columns": [
                        {"value": 1, "text": "Rarely"},
                        {"value": 2, "text": "Often"},
                    ],
                    "rows": [
                        {"value": "sleep", "text": "Sleeping badly"},
                        {"value": "eat", "text": "Eating less"},
                    ],
                },
            ],
        }
    ],
    "calculatedValues": [
        {"name": "total", "title": "Total score", "expression": "1"},
        {"name": "sub_score", "expression": "2"},
        {"name": "not_stored", "title": "Never shown", "expression": "3"},
    ],
}
ANSWERS = {
    "nickname": "Zed",
    "fruit": "a",
    "colours": ["Red", "g"],
    "agree": True,
    "notes_in_panel": "Inside a panel",
    "mood": {"sleep": 2, "eat": 1},
}
METRICS = {"total": 17, "sub_score": 4}


def text_of(content: bytes) -> str:
    pages = PdfReader(io.BytesIO(content)).pages
    return " ".join(" ".join(page.extract_text().split()) for page in pages)


@pytest.fixture
def submitted(catalog, owner, anon) -> dict:
    snapshot = catalog.qtype(owner, title="PHQ 9: Mood!", questionnaire_json=SURVEY)
    created = create_questionnaire(owner, snapshot["aggregateId"], name="Alice")
    assert submit(anon, created["shareToken"], ANSWERS, METRICS).status_code == 200
    return created


def pdf_url(questionnaire: dict) -> str:
    return f"/api/questionnaires/{questionnaire['id']}/pdf/"


def test_download(owner, submitted):
    response = owner.http.get(pdf_url(submitted), headers={"Origin": SPA_ORIGIN})
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF-")
    # The type's title made safe, and the server's date in UTC.
    today = datetime.now(UTC).date().isoformat()
    assert response.headers["content-disposition"] == (
        f'attachment; filename="PHQ-9-Mood-{today}.pdf"'
    )
    # The SPA is another origin, so it may read that header only when told.
    assert response.headers["access-control-allow-origin"] == SPA_ORIGIN
    exposed = response.headers["access-control-expose-headers"].lower()
    assert "content-disposition" in [h.strip() for h in exposed.split(",")]


def test_the_text_holds_the_response(owner, submitted):
    text = text_of(owner.http.get(pdf_url(submitted)).content)
    for expected in [
        "PHQ 9: Mood!",
        "Alice",
        "Your nickname",
        "Zed",
        "Favourite fruit",
        # Display labels, never the stored values.
        "Apple",
        "Colours you like",
        "Red, Green",
        "Do you agree",
        "Yes",
        # A question in a panel, titled by its name when it has no title.
        "notes_in_panel",
        "Inside a panel",
        "Left blank",
        "No answer",
        "Mood grid",
        "Sleeping badly",
        "Eating less",
        "Rarely",
        "Often",
        # Scores by their titles, or the name in title case.
        "Total score",
        "17",
        "Sub Score",
        "4",
    ]:
        assert expected in text, expected
    for absent in ["Hidden html block", "Never shown", "Banana"]:
        assert absent not in text, absent


def test_false_is_no(catalog, owner, anon):
    survey = {
        "pages": [{"elements": [{"type": "boolean", "name": "ok", "title": "OK?"}]}]
    }
    snapshot = catalog.qtype(owner, title="Short", questionnaire_json=survey)
    created = create_questionnaire(owner, snapshot["aggregateId"])
    submit(anon, created["shareToken"], {"ok": False})
    text = text_of(owner.http.get(pdf_url(created)).content)
    assert "OK? No" in text


def test_a_type_title_with_nothing_safe_is_response(catalog, owner, anon):
    snapshot = catalog.qtype(owner, title="!!!")
    created = create_questionnaire(owner, snapshot["aggregateId"])
    submit(anon, created["shareToken"])
    disposition = owner.http.get(pdf_url(created)).headers["content-disposition"]
    assert re.fullmatch(
        r'attachment; filename="response-\d{4}-\d\d-\d\d\.pdf"', disposition
    )


def test_a_long_title_is_cut_to_sixty(catalog, owner, anon):
    snapshot = catalog.qtype(owner, title="a" * 80)
    created = create_questionnaire(owner, snapshot["aggregateId"])
    submit(anon, created["shareToken"])
    disposition = owner.http.get(pdf_url(created)).headers["content-disposition"]
    assert f'filename="{"a" * 60}-' in disposition


def test_the_pdf_reads_the_snapshot(catalog, owner, submitted):
    """Edited after submission: the PDF still shows what was answered."""
    detail = owner.http.get(f"/api/questionnaires/{submitted['id']}/").json()
    catalog.apply(
        as_event(
            qtype_snapshot(
                owner.id,
                ref_id=detail["questionnaireTypeId"],
                version=2,
                title="PHQ 9: Mood!",
                questionnaire_json={"pages": []},
            )
        )
    )
    assert "Favourite fruit" in text_of(owner.http.get(pdf_url(submitted)).content)


def test_not_submitted_is_400(owner, qtype):
    created = create_questionnaire(owner, qtype["aggregateId"])
    response = owner.http.get(pdf_url(created))
    assert response.status_code == 400
    assert response.json() == {"detail": "This questionnaire has not been submitted."}


def test_another_owners_pdf_is_404(other, submitted):
    assert other.http.get(pdf_url(submitted)).status_code == 404


def test_asking_for_a_pdf_by_accept(owner, submitted):
    response = owner.http.get(pdf_url(submitted), headers={"Accept": "application/pdf"})
    assert response.status_code == 200
    assert response.content.startswith(b"%PDF-")
