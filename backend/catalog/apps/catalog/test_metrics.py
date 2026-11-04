"""The outbox gauges and the retire counter (#13)."""

from datetime import timedelta

import pytest
from common.peers import PeerUnavailable
from django.test import Client, override_settings
from django.utils import timezone
from freezegun import freeze_time
from prometheus_client import REGISTRY

from .factories import QuestionnaireTypeFactory
from .models import OutboxEvent

pytestmark = pytest.mark.django_db


def sample(name: str) -> float:
    return REGISTRY.get_sample_value(name) or 0


class Down:
    def retire(self, kind, ref_id):  # noqa: ARG002
        raise PeerUnavailable("instances is down")


def scrape() -> str:
    client = Client(REMOTE_ADDR="127.0.0.1")
    with override_settings(METRICS_ALLOWED_CIDRS=["127.0.0.1/32"]):
        response = client.get("/metrics")
    assert response.status_code == 200
    return response.content.decode()


def test_scrape_reports_the_pending_outbox():
    now = timezone.now()
    with freeze_time(now - timedelta(seconds=90)):
        OutboxEvent.objects.create(
            event_type="user.deleted",
            aggregate_id="11111111-1111-1111-1111-111111111111",
            version=1,
            data={},
        )
    with freeze_time(now):
        body = scrape()
    assert "app_outbox_pending_events 1.0" in body
    assert "app_outbox_oldest_pending_seconds 90.0" in body


def test_an_empty_outbox_reads_zero():
    body = scrape()
    assert "app_outbox_pending_events 0.0" in body
    assert "app_outbox_oldest_pending_seconds 0.0" in body


def test_a_delete_that_cannot_ask_is_counted(auth_client, user, settings):
    settings.INSTANCES_CLIENT = f"{__name__}.Down"
    qtype = QuestionnaireTypeFactory(owner=user)
    before = sample("app_retire_failures_total")
    assert (
        auth_client.delete(f"/api/questionnaire-types/{qtype.pk}/").status_code == 503
    )
    assert sample("app_retire_failures_total") == before + 1
