import jwt
import pytest
from common.dev_keys import DEV_SIGNING_KEY
from django.utils import timezone
from rest_framework.test import APIClient

from .factories import QuestionnaireTypeFactory, make_owner


def type_changed(ref, version=None, **changes):
    """The event `catalog` sends when this copy's source is edited."""
    fields = {
        "title": ref.title,
        "questionnaireJson": ref.questionnaire_json,
        **changes,
    }
    return {
        "id": "00000000-0000-0000-0000-000000000000",
        "type": "questionnaire_type.changed",
        "aggregateId": str(ref.pk),
        "version": ref.version + 1 if version is None else version,
        "data": {
            "ownerId": str(ref.owner_id),
            "createdAt": ref.created_at.isoformat(),
            "updatedAt": timezone.now().isoformat(),
            **fields,
        },
    }


def access_token(owner_id, **claims) -> str:
    """As `catalog` issues them. This service cannot: it holds no private key."""
    now = timezone.now()
    payload = {
        "token_type": "access",
        "iat": now,
        "exp": now + timezone.timedelta(minutes=5),
        "jti": "test",
        "user_id": str(owner_id),
        **claims,
    }
    return jwt.encode(payload, DEV_SIGNING_KEY, algorithm="RS256")


def bearer(token: str) -> APIClient:
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


@pytest.fixture
def user(db):  # noqa: ARG001
    return make_owner()


@pytest.fixture
def other_user(db):  # noqa: ARG001
    return make_owner()


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def auth_client(user):
    client = APIClient()
    client.force_authenticate(user)
    return client


@pytest.fixture
def other_client(other_user):
    client = APIClient()
    client.force_authenticate(other_user)
    return client


@pytest.fixture
def qtype(user):
    return QuestionnaireTypeFactory(owner=user)


@pytest.fixture
def on_commit(django_capture_on_commit_callbacks):
    return lambda: django_capture_on_commit_callbacks(execute=True)


@pytest.fixture
def internal_client(settings):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {settings.PEER_INBOUND_TOKEN}")
    return client
