"""`instances` verifies tokens statelessly, with a public key only (#13)."""

import uuid
from datetime import timedelta

import jwt
import pytest
from common.dev_keys import DEV_VERIFYING_KEY
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend

from . import refs, services
from .conftest import access_token, bearer
from .factories import (
    BatteryTypeFactory,
    QuestionnaireFactory,
    QuestionnaireTypeFactory,
)
from .models import (
    Battery,
    BlockedOwner,
    Questionnaire,
    QuestionnaireTypeRef,
)

pytestmark = pytest.mark.django_db

SUMMARY = "/api/dashboard/"
QUESTIONNAIRES = "/api/questionnaires/"


def forged(algorithm: str, key, **claims) -> str:
    payload = {
        "token_type": "access",
        "exp": timezone.now() + timedelta(minutes=5),
        "jti": uuid.uuid4().hex,
        "user_id": str(uuid.uuid4()),
        **claims,
    }
    return jwt.encode(payload, key, algorithm=algorithm)


def user_event(action, owner_id, version=1):
    return {
        "type": f"user.{action}",
        "aggregateId": str(owner_id),
        "version": version,
        "data": {},
    }


def test_valid_token_needs_no_user_row(db):  # noqa: ARG001
    # No such user exists here, and the service does not need one.
    response = bearer(access_token(uuid.uuid4())).get(QUESTIONNAIRES)
    assert response.status_code == 200
    assert response.data["results"] == []


def test_instances_settings_hold_no_signing_key():
    assert settings.SIMPLE_JWT["SIGNING_KEY"] == ""
    assert settings.SIMPLE_JWT["VERIFYING_KEY"]


def test_a_public_key_is_enough_to_verify(user):
    backend = TokenBackend("RS256", verifying_key=DEV_VERIFYING_KEY)
    assert backend.decode(access_token(user.pk))["user_id"] == str(user.pk)


def test_token_signed_with_another_key_is_refused(user):
    other = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = forged("RS256", other, user_id=str(user.pk))
    assert bearer(token).get(SUMMARY).status_code == 401


def test_hs256_token_is_refused(user):
    token = forged("HS256", settings.SECRET_KEY, user_id=str(user.pk))
    assert bearer(token).get(SUMMARY).status_code == 401


def test_token_signed_with_the_public_key_as_a_secret_is_refused(user, mocker):
    # Algorithm confusion: PyJWT refuses a PEM as an HMAC secret, so sign by hand.
    mocker.patch(
        "jwt.algorithms.HMACAlgorithm.prepare_key",
        side_effect=lambda key: key.encode(),
    )
    token = forged("HS256", DEV_VERIFYING_KEY, user_id=str(user.pk))
    mocker.stopall()
    assert bearer(token).get(SUMMARY).status_code == 401


def test_token_with_a_bad_user_id_is_refused(db):  # noqa: ARG001
    assert bearer(access_token("not-a-uuid")).get(SUMMARY).status_code == 401


def test_blocked_check_runs_before_cache(user, qtype, cache_on, on_commit):  # noqa: ARG001
    QuestionnaireFactory(questionnaire_type=qtype)
    client = bearer(access_token(user.pk))
    assert client.get(SUMMARY).status_code == 200

    cache_get = cache.get
    calls = []
    cache.get = lambda *args, **kwargs: (
        calls.append(args),
        cache_get(*args, **kwargs),
    )[1]
    try:
        refs.apply_event(user_event("deactivated", user.pk))
        assert client.get(SUMMARY).status_code == 401
    finally:
        del cache.get
    assert calls == []


def test_reactivated_owner_is_let_back_in(user):
    client = bearer(access_token(user.pk))
    refs.apply_event(user_event("deactivated", user.pk, version=1))
    assert client.get(QUESTIONNAIRES).status_code == 401
    refs.apply_event(user_event("reactivated", user.pk, version=2))
    assert client.get(QUESTIONNAIRES).status_code == 200


def test_older_deactivation_cannot_block_again(user):
    refs.apply_event(user_event("reactivated", user.pk, version=5))
    assert (
        refs.apply_event(user_event("deactivated", user.pk, version=4)) == refs.IGNORED
    )
    assert not BlockedOwner.objects.get(pk=user.pk).blocked


def test_user_deleted_event_removes_owner_rows(user, other_user):
    qtype = QuestionnaireTypeFactory(owner=user)
    services.create_battery(BatteryTypeFactory(owner=user, questionnaire_types=[qtype]))
    QuestionnaireFactory(questionnaire_type=qtype)
    theirs = QuestionnaireFactory(
        questionnaire_type=QuestionnaireTypeFactory(owner=other_user)
    )
    client = bearer(access_token(user.pk))

    refs.apply_event(user_event("deleted", user.pk))

    assert not Questionnaire.objects.filter(owner_id=user.pk).exists()
    assert not Battery.objects.filter(owner_id=user.pk).exists()
    assert not QuestionnaireTypeRef.objects.filter(owner_id=user.pk).exists()
    assert Questionnaire.objects.filter(pk=theirs.pk).exists()
    # Their token still verifies, and must not work.
    assert client.get(QUESTIONNAIRES).status_code == 401


def test_late_type_event_cannot_recreate_a_deleted_owners_copy(user):
    refs.apply_event(user_event("deleted", user.pk))
    event = {
        "type": "questionnaire_type.changed",
        "aggregateId": str(uuid.uuid4()),
        "version": 1,
        "data": {
            "ownerId": str(user.pk),
            "title": "Late",
            "questionnaireJson": {},
            "createdAt": timezone.now().isoformat(),
            "updatedAt": timezone.now().isoformat(),
        },
    }
    assert refs.apply_event(event) == refs.IGNORED
    assert not QuestionnaireTypeRef.objects.exists()


def test_deleted_owner_stays_blocked_whatever_arrives_late(user):
    refs.apply_event(user_event("deleted", user.pk, version=5))
    assert (
        refs.apply_event(user_event("reactivated", user.pk, version=9)) == refs.IGNORED
    )
    assert BlockedOwner.objects.get(pk=user.pk).blocked


def test_authenticated_request_costs_exactly_the_blocked_check(user, qtype):
    QuestionnaireFactory(questionnaire_type=qtype)
    forced = APIClient()
    forced.force_authenticate(user)
    with CaptureQueriesContext(connection) as without_auth:
        assert forced.get(QUESTIONNAIRES).status_code == 200
    with CaptureQueriesContext(connection) as with_auth:
        client = bearer(access_token(user.pk))
        assert client.get(QUESTIONNAIRES).status_code == 200
    assert len(with_auth) == len(without_auth) + 1


def test_tests_never_touch_a_real_redis():
    # `cache_on` calls cache.clear(), which on Redis empties the whole database.
    backend = settings.CACHES["default"]["BACKEND"]
    assert backend == "django.core.cache.backends.locmem.LocMemCache"
    assert settings.CACHES["default"]["KEY_PREFIX"] == "instances"
