"""Caching of the dashboard endpoints (#11)."""

from datetime import UTC, datetime, timedelta

import pytest
from django.test.utils import override_settings
from freezegun import freeze_time
from redis.exceptions import ConnectionError as RedisConnectionError
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.utils import cache as cache_module

from . import services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from .views import DASHBOARD_CACHE_SECONDS

SUMMARY = "/api/dashboard/"
SCORES = "/api/dashboard/scores/"
NOW = datetime(2026, 10, 30, 12, 0, tzinfo=UTC)

pytestmark = pytest.mark.usefixtures("cache_on")


def submit(questionnaire):
    return services.submit_questionnaire(questionnaire, {"q1": "a"}, {"total": 3})


def sent(client, **params):
    response = client.get(SUMMARY, params)
    assert response.status_code == 200, response.content
    return response.json()["kpis"]["questionnairesSent"]


def score_values(client, qtype):
    response = client.get(SCORES, {"questionnaireType": qtype.pk})
    assert response.status_code == 200, response.content
    return [p["value"] for m in response.json()["metrics"] for p in m["points"]]


@pytest.fixture
def rows(user, qtype):
    QuestionnaireFactory(questionnaire_type=qtype)
    submit(QuestionnaireFactory(questionnaire_type=qtype))
    BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    return qtype


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


# ── Hits ──────────────────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [SUMMARY, SCORES])
def test_hit_matches_miss_byte_for_byte(auth_client, rows, url):
    params = {"questionnaireType": rows.pk, "days": 7}
    with freeze_time(NOW):
        with override_settings(CACHE_ENABLED=False):
            uncached = auth_client.get(url, params)
        miss = auth_client.get(url, params)
        hit = auth_client.get(url, params)
    assert uncached.status_code == 200
    assert miss.content == uncached.content
    assert hit.content == uncached.content


def test_hit_skips_dashboard_queries(auth_client, rows, django_assert_num_queries):  # noqa: ARG001
    auth_client.get(SUMMARY)
    # auth_client is force-authenticated, so no user lookup.
    with django_assert_num_queries(0):
        auth_client.get(SUMMARY)


def test_hit_on_a_type_filter_costs_only_its_validation(
    auth_client, rows, django_assert_num_queries
):
    for url in (SUMMARY, SCORES):
        auth_client.get(url, {"questionnaireType": rows.pk})
        with django_assert_num_queries(1):
            auth_client.get(url, {"questionnaireType": rows.pk})


def test_params_do_not_share_an_entry(auth_client, qtype):
    other_type = QuestionnaireTypeFactory(owner=qtype.owner)
    QuestionnaireFactory(questionnaire_type=qtype)
    assert sent(auth_client) == 1
    assert sent(auth_client, questionnaireType=other_type.pk) == 0
    assert sent(auth_client, days=7) == 1


# ── Tenants and access ────────────────────────────────────────────────────────


def test_other_owner_never_sees_cached_dashboard(auth_client, other_client, rows):  # noqa: ARG001
    assert sent(auth_client) == 2
    assert sent(other_client) == 0
    assert sent(auth_client) == 2


def test_other_owner_never_sees_cached_scores(
    auth_client, other_client, user, other_user
):
    # Each owner's own type, and the same params apart from it.
    mine = QuestionnaireTypeFactory(owner=user)
    theirs = QuestionnaireTypeFactory(owner=other_user)
    submit(QuestionnaireFactory(questionnaire_type=mine))
    assert score_values(auth_client, mine) == [3]
    assert score_values(other_client, theirs) == []


@pytest.mark.parametrize("url", [SUMMARY, SCORES])
def test_foreign_questionnaire_type_is_still_400_on_a_cached_key(
    auth_client, other_client, rows, url
):
    params = {"questionnaireType": rows.pk}
    assert auth_client.get(url, params).status_code == 200
    assert other_client.get(url, params).status_code == 400


def test_deactivated_user_is_refused_after_caching(user, rows):  # noqa: ARG001
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {AccessToken.for_user(user)}")
    assert client.get(SUMMARY).status_code == 200
    user.is_active = False
    user.save()
    assert client.get(SUMMARY).status_code == 401


# ── Invalidation ──────────────────────────────────────────────────────────────


def test_type_create_invalidates(auth_client, on_commit):
    def titles():
        summary = auth_client.get(SUMMARY).json()
        return [t["title"] for t in summary["byQuestionnaireType"]]

    assert titles() == []
    with on_commit():
        auth_client.post("/api/questionnaire-types/", {"title": "New"}, format="json")
    assert titles() == ["New"]


def test_type_update_invalidates(auth_client, rows, on_commit):
    auth_client.get(SUMMARY)
    with on_commit():
        auth_client.patch(
            f"/api/questionnaire-types/{rows.pk}/", {"title": "Renamed"}, format="json"
        )
    summary = auth_client.get(SUMMARY).json()
    assert summary["byQuestionnaireType"][0]["title"] == "Renamed"


def test_type_update_invalidates_score_labels(auth_client, qtype, on_commit):
    submit(QuestionnaireFactory(questionnaire_type=qtype))
    params = {"questionnaireType": qtype.pk}
    assert auth_client.get(SCORES, params).json()["metrics"][0]["label"] == "total"
    definition = {"calculatedValues": [{"name": "total", "title": "Total score"}]}
    with on_commit():
        auth_client.patch(
            f"/api/questionnaire-types/{qtype.pk}/",
            {"questionnaireJson": definition},
            format="json",
        )
    metric = auth_client.get(SCORES, params).json()["metrics"][0]
    assert metric["label"] == "Total score"


def test_battery_type_create_and_update_invalidate(auth_client, user, on_commit):
    qtype = QuestionnaireTypeFactory(owner=user)

    def titles(**params):
        summary = auth_client.get(SUMMARY, params).json()
        return [t["title"] for t in summary["byBatteryType"]]

    assert titles() == []
    with on_commit():
        created = auth_client.post(
            "/api/battery-types/", {"title": "B"}, format="json"
        ).json()
    assert titles() == ["B"]

    # The filter reads the type's items, which are written after the battery type.
    assert titles(questionnaireType=qtype.pk) == []
    with on_commit():
        auth_client.patch(
            f"/api/battery-types/{created['id']}/",
            {"questionnaireTypeIds": [str(qtype.pk)]},
            format="json",
        )
    assert titles(questionnaireType=qtype.pk) == ["B"]


def test_questionnaire_delete_invalidates(auth_client, qtype, on_commit):
    questionnaire = QuestionnaireFactory(questionnaire_type=qtype)
    assert sent(auth_client) == 1
    with on_commit():
        response = auth_client.delete(f"/api/questionnaires/{questionnaire.pk}/")
    assert response.status_code == 204
    assert sent(auth_client) == 0


def test_battery_delete_invalidates(auth_client, user, qtype, on_commit):
    battery_type = BatteryTypeFactory(owner=user, questionnaire_types=[qtype])
    battery = services.create_battery(battery_type)

    def total():
        return auth_client.get(SUMMARY).json()["kpis"]["batteriesTotal"]

    assert total() == 1
    with on_commit():
        response = auth_client.delete(f"/api/batteries/{battery.pk}/")
    assert response.status_code == 204
    assert total() == 0


def test_failed_delete_does_not_invalidate(auth_client, qtype, on_commit):
    QuestionnaireFactory(questionnaire_type=qtype)
    assert sent(auth_client) == 1
    QuestionnaireFactory(questionnaire_type=qtype)
    with on_commit():
        response = auth_client.delete(f"/api/questionnaire-types/{qtype.pk}/")
    assert response.status_code == 409
    # Still the cached count: the failed delete did not bump the generation.
    assert sent(auth_client) == 1


def test_another_owners_write_does_not_invalidate(
    auth_client, other_client, qtype, on_commit
):
    QuestionnaireFactory(questionnaire_type=qtype)
    assert sent(auth_client) == 1
    QuestionnaireFactory(questionnaire_type=qtype)
    with on_commit():
        other_client.post("/api/questionnaire-types/", {"title": "X"}, format="json")
    assert sent(auth_client) == 1


# ── The staleness contract ────────────────────────────────────────────────────


def test_submit_is_visible_after_ttl(auth_client, api_client, qtype, on_commit):
    questionnaire = QuestionnaireFactory(questionnaire_type=qtype)

    def submitted():
        return auth_client.get(SUMMARY).json()["kpis"]["questionnairesSubmitted"]

    with freeze_time(NOW) as clock:
        assert submitted() == 0
        with on_commit():
            response = api_client.patch(
                f"/api/questionnaires/by-token/{questionnaire.share_token}/submit/",
                {"answers": {"q1": "a"}},
                format="json",
            )
        assert response.status_code == 200
        assert submitted() == 0  # within the TTL
        clock.tick(timedelta(seconds=DASHBOARD_CACHE_SECONDS + 1))
        assert submitted() == 1


# ── Failing open ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize("url", [SUMMARY, SCORES])
def test_redis_down_still_returns_200(auth_client, rows, mocker, url):
    broken = mocker.patch.object(cache_module, "cache")
    broken.get_or_set.side_effect = RedisConnectionError("connection refused")
    response = auth_client.get(url, {"questionnaireType": rows.pk})
    assert response.status_code == 200
    assert broken.get_or_set.called


def test_redis_down_does_not_fail_a_write(auth_client, rows, mocker, on_commit):
    broken = mocker.patch.object(cache_module, "cache")
    broken.set.side_effect = RedisConnectionError("connection refused")
    with on_commit():
        response = auth_client.patch(
            f"/api/questionnaire-types/{rows.pk}/", {"title": "X"}, format="json"
        )
    assert response.status_code == 200
    assert broken.set.called
