import pytest
from rest_framework.test import APIClient

from .factories import QuestionnaireTypeFactory, UserFactory


@pytest.fixture
def user(db):  # noqa: ARG001
    return UserFactory()


@pytest.fixture
def other_user(db):  # noqa: ARG001
    return UserFactory()


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
