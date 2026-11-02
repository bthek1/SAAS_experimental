"""Query counts on the paths the k6 scenarios load (#9).

Each endpoint must cost the same number of queries for one row as for many,
so an N+1 fails here instead of showing up as a throughput collapse under load.
(The dashboard endpoints have their own checks in test_dashboard.py.)
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from . import services
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)


def make_rows(user, n):
    """n of everything the list endpoints return; returns the last of each."""
    qtypes = [QuestionnaireTypeFactory(owner=user) for _ in range(n)]
    btype = BatteryTypeFactory(owner=user, questionnaire_types=qtypes[:2])
    for _ in range(n - 1):
        BatteryTypeFactory(owner=user, questionnaire_types=qtypes[:2])
    batteries = [services.create_battery(btype) for _ in range(n)]
    questionnaires = [QuestionnaireFactory(questionnaire_type=qt) for qt in qtypes]
    return {"q": questionnaires[-1], "b": batteries[-1]}


ENDPOINTS = {
    "questionnaire-list": "/api/questionnaires/",
    "questionnaire-detail": "/api/questionnaires/{q.id}/",
    "questionnaire-type-list": "/api/questionnaire-types/",
    "battery-type-list": "/api/battery-types/",
    "battery-list": "/api/batteries/",
    "battery-detail": "/api/batteries/{b.id}/",
    "questionnaire-by-token": "/api/questionnaires/by-token/{q.share_token}/",
    "battery-by-token": "/api/batteries/by-token/{b.share_token}/",
}


def count_queries(client, url):
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, response.content
    return len(ctx.captured_queries)


@pytest.mark.parametrize("name", ENDPOINTS)
def test_query_count_does_not_grow_with_rows(
    name, auth_client, user, other_client, other_user
):
    url = ENDPOINTS[name]
    one = count_queries(auth_client, url.format(**make_rows(user, 1)))
    many = count_queries(other_client, url.format(**make_rows(other_user, 6)))
    assert many == one


def test_submit_query_count(api_client, user, django_assert_max_num_queries):
    questionnaire = QuestionnaireFactory(
        questionnaire_type=QuestionnaireTypeFactory(owner=user)
    )
    url = f"/api/questionnaires/by-token/{questionnaire.share_token}/submit/"
    with django_assert_max_num_queries(5):
        response = api_client.patch(
            url, {"answers": {"q1": "a"}, "metrics": {"total": 3}}, format="json"
        )
    assert response.status_code == 200
