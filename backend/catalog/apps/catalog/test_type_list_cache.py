"""Caching of the questionnaire-type and battery-type lists (#11)."""

import pytest
from django.test.utils import override_settings

from .factories import BatteryTypeFactory, QuestionnaireTypeFactory

QTYPES = "/api/questionnaire-types/"
BTYPES = "/api/battery-types/"

pytestmark = pytest.mark.usefixtures("cache_on")

FACTORIES = {QTYPES: QuestionnaireTypeFactory, BTYPES: BatteryTypeFactory}
both_lists = pytest.mark.parametrize("url", [QTYPES, BTYPES])


def titles(client, url, **params):
    response = client.get(url, params)
    assert response.status_code == 200, response.content
    return [row["title"] for row in response.json()["results"]]


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


@both_lists
def test_hit_matches_miss_byte_for_byte(auth_client, user, url):
    for _ in range(3):
        FACTORIES[url](owner=user)
    with override_settings(CACHE_ENABLED=False):
        uncached = auth_client.get(url, {"page_size": 2})
    miss = auth_client.get(url, {"page_size": 2})
    hit = auth_client.get(url, {"page_size": 2})
    assert miss.content == uncached.content
    assert hit.content == uncached.content


@both_lists
def test_hit_runs_no_queries(auth_client, user, url, django_assert_num_queries):
    FACTORIES[url](owner=user)
    auth_client.get(url)
    # auth_client is force-authenticated, so no user lookup.
    with django_assert_num_queries(0):
        auth_client.get(url)


@both_lists
def test_other_owner_never_sees_cached_list(auth_client, other_client, user, url):
    FACTORIES[url](owner=user, title="Mine")
    assert titles(auth_client, url) == ["Mine"]
    assert titles(other_client, url) == []


def test_the_two_lists_do_not_share_an_entry(auth_client, user):
    QuestionnaireTypeFactory(owner=user, title="A type")
    BatteryTypeFactory(owner=user, title="A battery")
    assert titles(auth_client, QTYPES) == ["A type"]
    assert titles(auth_client, BTYPES) == ["A battery"]


@both_lists
def test_next_link_uses_the_requesting_host(auth_client, user, url):
    for _ in range(2):
        FACTORIES[url](owner=user)
    params = {"page_size": 1}
    first = auth_client.get(url, params, HTTP_HOST="localhost").json()
    second = auth_client.get(url, params, HTTP_HOST="127.0.0.1").json()
    assert first["next"].startswith("http://localhost/")
    assert second["next"].startswith("http://127.0.0.1/")


@both_lists
def test_page_size_is_part_of_the_key(auth_client, user, url):
    for _ in range(3):
        FACTORIES[url](owner=user)
    assert len(titles(auth_client, url, page_size=1)) == 1
    assert len(titles(auth_client, url, page_size=2)) == 2
    assert len(titles(auth_client, url)) == 3


@both_lists
def test_page_is_part_of_the_key(auth_client, user, url):
    for _ in range(2):
        FACTORIES[url](owner=user)
    first = titles(auth_client, url, page_size=1, page=1)
    second = titles(auth_client, url, page_size=1, page=2)
    assert first != second


@both_lists
def test_out_of_range_page_is_404(auth_client, user, url):
    FACTORIES[url](owner=user)
    assert auth_client.get(url, {"page": 9}).status_code == 404
    assert auth_client.get(url, {"page": 9}).status_code == 404


def test_a_page_that_appears_is_not_stuck_on_404(auth_client, user, on_commit):
    QuestionnaireTypeFactory(owner=user)
    assert auth_client.get(QTYPES, {"page": 2, "page_size": 1}).status_code == 404
    with on_commit():
        auth_client.post(QTYPES, {"title": "Second"}, format="json")
    assert auth_client.get(QTYPES, {"page": 2, "page_size": 1}).status_code == 200


def test_unauthenticated_is_refused(api_client, db):  # noqa: ARG001
    assert api_client.get(QTYPES).status_code == 401


# ── Every write through the API shows up at once ──────────────────────────────


def create_qtype(client, _user):
    client.post(QTYPES, {"title": "After"}, format="json")


def patch_qtype(client, user):
    client.patch(f"{QTYPES}{user.qt.pk}/", {"title": "After"}, format="json")


def delete_qtype(client, user):
    client.delete(f"{QTYPES}{user.qt.pk}/")


def create_btype(client, _user):
    client.post(BTYPES, {"title": "After"}, format="json")


def patch_btype(client, user):
    client.patch(f"{BTYPES}{user.bt.pk}/", {"title": "After"}, format="json")


def delete_btype(client, user):
    client.delete(f"{BTYPES}{user.bt.pk}/")


@pytest.mark.parametrize(
    ("url", "write", "expected"),
    [
        (QTYPES, create_qtype, {"After", "Before", "Used"}),
        (QTYPES, patch_qtype, {"After", "Used"}),
        (QTYPES, delete_qtype, {"Used"}),
        (BTYPES, create_btype, {"After", "Before"}),
        (BTYPES, patch_btype, {"After"}),
        (BTYPES, delete_btype, set()),
    ],
    ids=["qt-create", "qt-patch", "qt-delete", "bt-create", "bt-patch", "bt-delete"],
)
def test_every_write_shows_up_immediately(
    auth_client, user, on_commit, url, write, expected
):
    used = QuestionnaireTypeFactory(owner=user, title="Used")
    user.qt = QuestionnaireTypeFactory(owner=user, title="Before")
    user.bt = BatteryTypeFactory(owner=user, title="Before", questionnaire_types=[used])
    titles(auth_client, url)
    with on_commit():
        write(auth_client, user)
    assert set(titles(auth_client, url)) == expected


def test_changed_questionnaire_type_ids_show_up_immediately(
    auth_client, user, on_commit
):
    first = QuestionnaireTypeFactory(owner=user)
    second = QuestionnaireTypeFactory(owner=user)
    battery_type = BatteryTypeFactory(owner=user, questionnaire_types=[first])

    def ids():
        return auth_client.get(BTYPES).json()["results"][0]["questionnaireTypeIds"]

    assert ids() == [str(first.pk)]
    with on_commit():
        auth_client.patch(
            f"{BTYPES}{battery_type.pk}/",
            {"questionnaireTypeIds": [str(second.pk)]},
            format="json",
        )
    assert ids() == [str(second.pk)]
