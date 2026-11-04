import uuid

import pytest

from .factories import QuestionnaireTypeFactory
from .models import QuestionnaireType


@pytest.mark.django_db
class TestQuestionnaireType:
    def test_id_is_uuid(self, qtype):
        assert isinstance(qtype.id, uuid.UUID)

    def test_str_is_title(self, qtype):
        assert str(qtype) == qtype.title

    def test_ordering_newest_first(self, user):
        first = QuestionnaireTypeFactory(owner=user)
        second = QuestionnaireTypeFactory(owner=user)
        assert list(QuestionnaireType.objects.all()) == [second, first]
