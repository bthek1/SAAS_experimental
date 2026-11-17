"""Share links: what an anonymous respondent reads and submits.

No authentication at all, so a stale token in the respondent's browser cannot turn
into a 401. A questionnaire is submitted once; the SPA treats the 409 as "already
submitted".
"""

import re

import pytest

from .support import (
    TIMESTAMP,
    as_event,
    create_battery,
    create_questionnaire,
    new_id,
    qtype_snapshot,
    submit,
)

QUESTIONS = {"pages": [{"name": "p1", "elements": [{"type": "text", "name": "q1"}]}]}


def by_token(share_token: str) -> str:
    return f"/api/questionnaires/by-token/{share_token}/"


@pytest.fixture
def questionnaire(catalog, owner) -> tuple[dict, dict]:
    snapshot = catalog.qtype(owner, title="Check-in", questionnaire_json=QUESTIONS)
    return create_questionnaire(owner, snapshot["aggregateId"], name="Alice"), snapshot


def test_read(anon, questionnaire):
    created, _ = questionnaire
    response = anon.get(by_token(created["shareToken"]))
    assert response.status_code == 200
    # Only what a respondent needs: no owner, no answers.
    assert response.json() == {
        "id": created["id"],
        "name": "Alice",
        "questionnaireTypeTitle": "Check-in",
        "questionnaireJson": QUESTIONS,
        "submittedAt": None,
    }


def test_read_ignores_any_token(anon, questionnaire):
    created, _ = questionnaire
    headers = {"Authorization": "Bearer not-a-real-token"}
    assert anon.get(by_token(created["shareToken"]), headers=headers).status_code == 200


def test_before_submit_the_live_definition_is_shown(
    catalog, owner, anon, questionnaire
):
    created, snapshot = questionnaire
    edited = {"pages": [{"name": "p2", "elements": []}]}
    catalog.apply(
        as_event(
            qtype_snapshot(
                owner.id,
                ref_id=snapshot["aggregateId"],
                version=2,
                title="Edited",
                questionnaire_json=edited,
            )
        )
    )
    body = anon.get(by_token(created["shareToken"])).json()
    assert body["questionnaireJson"] == edited
    assert body["questionnaireTypeTitle"] == "Edited"


def test_submit(anon, questionnaire):
    created, _ = questionnaire
    response = submit(anon, created["shareToken"], {"q1": "hello"}, {"totalScore": 7})
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "id",
        "name",
        "questionnaireTypeTitle",
        "questionnaireJson",
        "submittedAt",
    }
    assert re.match(TIMESTAMP, body["submittedAt"])
    assert body["questionnaireJson"] == QUESTIONS


def test_submit_stores_answers_and_metrics(owner, anon, questionnaire):
    created, _ = questionnaire
    submit(anon, created["shareToken"], {"q1": "hello"}, {"totalScore": 7})
    stored = owner.http.get(f"/api/questionnaires/{created['id']}/").json()
    assert stored["answers"] == {"q1": "hello"}
    assert stored["metrics"] == {"totalScore": 7}


def test_metrics_default_to_empty(owner, anon, questionnaire):
    created, _ = questionnaire
    assert submit(anon, created["shareToken"], {}).status_code == 200
    stored = owner.http.get(f"/api/questionnaires/{created['id']}/").json()
    assert stored["metrics"] == {}


def test_a_second_submit_is_409(owner, anon, questionnaire):
    created, _ = questionnaire
    assert submit(anon, created["shareToken"], {"q1": "a"}).status_code == 200
    response = submit(anon, created["shareToken"], {"q1": "b"})
    assert response.status_code == 409
    assert response.json() == {"detail": "Already submitted."}
    stored = owner.http.get(f"/api/questionnaires/{created['id']}/").json()
    assert stored["answers"] == {"q1": "a"}


@pytest.mark.parametrize(
    ("body", "field"),
    [
        ({"answers": [1, 2]}, "answers"),
        ({"answers": "text"}, "answers"),
        ({}, "answers"),
        ({"answers": None}, "answers"),
        ({"answers": {}, "metrics": [1]}, "metrics"),
    ],
)
def test_submit_validation(anon, questionnaire, body, field):
    created, _ = questionnaire
    url = f"{by_token(created['shareToken'])}submit/"
    response = anon.patch(url, json=body)
    assert response.status_code == 400
    assert set(response.json()) == {field}
    # Nothing was stored: a valid submit still works.
    assert submit(anon, created["shareToken"], {}).status_code == 200


def test_submit_is_patch_only(anon, questionnaire):
    created, _ = questionnaire
    url = f"{by_token(created['shareToken'])}submit/"
    assert anon.post(url, json={"answers": {}}).status_code == 405
    assert anon.put(url, json={"answers": {}}).status_code == 405


def test_the_snapshot_survives_a_type_edit(catalog, owner, anon, questionnaire):
    created, snapshot = questionnaire
    submit(anon, created["shareToken"], {"q1": "a"})
    catalog.apply(
        as_event(
            qtype_snapshot(
                owner.id,
                ref_id=snapshot["aggregateId"],
                version=2,
                questionnaire_json={"pages": []},
            )
        )
    )
    # The respondent sees the definition it was answered against.
    body = anon.get(by_token(created["shareToken"])).json()
    assert body["questionnaireJson"] == QUESTIONS
    stored = owner.http.get(f"/api/questionnaires/{created['id']}/").json()
    assert stored["questionnaireJsonSnapshot"] == QUESTIONS


@pytest.mark.parametrize("share_token", [new_id(), "not-a-uuid"])
def test_an_unknown_token_is_404(anon, share_token):
    assert anon.get(by_token(share_token)).status_code == 404
    assert submit(anon, share_token, {}).status_code == 404
    assert anon.get(f"/api/batteries/by-token/{share_token}/").status_code == 404


def test_a_questionnaire_id_is_not_a_share_token(anon, questionnaire):
    created, _ = questionnaire
    assert anon.get(by_token(created["id"])).status_code == 404


def test_owner_endpoints_stay_private(anon, questionnaire):
    created, _ = questionnaire
    assert anon.get(f"/api/questionnaires/{created['id']}/").status_code == 401


def test_battery_by_token(catalog, owner, anon):
    a = catalog.qtype(owner, title="A")["aggregateId"]
    b = catalog.qtype(owner, title="B")["aggregateId"]
    battery = create_battery(
        owner, catalog.btype(owner, [b, a], title="Intake")["aggregateId"], name="Bob"
    )
    response = anon.get(f"/api/batteries/by-token/{battery['shareToken']}/")
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "id": battery["id"],
        "name": "Bob",
        "batteryTypeName": "Intake",
        "questionnaires": [
            {
                "order": slot["order"],
                "shareToken": slot["shareToken"],
                "questionnaireTypeName": slot["questionnaireTypeName"],
                "submittedAt": None,
            }
            for slot in battery["questionnaires"]
        ],
        "isComplete": False,
    }
    assert [slot["questionnaireTypeName"] for slot in body["questionnaires"]] == [
        "B",
        "A",
    ]


def test_battery_completes_after_every_slot(catalog, owner, anon, qtype):
    btype = catalog.btype(owner, [qtype["aggregateId"]] * 2)
    battery = create_battery(owner, btype["aggregateId"])
    url = f"/api/batteries/by-token/{battery['shareToken']}/"
    for slot in anon.get(url).json()["questionnaires"]:
        assert submit(anon, slot["shareToken"]).status_code == 200
    body = anon.get(url).json()
    assert body["isComplete"] is True
    assert all(re.match(TIMESTAMP, s["submittedAt"]) for s in body["questionnaires"])
