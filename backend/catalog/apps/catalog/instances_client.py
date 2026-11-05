"""How `catalog` reaches `instances` over HTTP (#13)."""

from common.peers import PeerUnavailable, RefInUse, peer_request
from django.conf import settings


class HttpInstances:
    def send_event(self, event: dict) -> None:
        response = peer_request(
            "POST", settings.INSTANCES_INTERNAL_URL, "/internal/events/", json=event
        )
        if response.status_code != 200:
            raise ValueError(f"event refused: HTTP {response.status_code}")

    def retire(self, kind: str, ref_id) -> None:
        response = peer_request(
            "POST",
            settings.INSTANCES_INTERNAL_URL,
            f"/internal/refs/{kind}/{ref_id}/retire/",
        )
        if response.status_code == 409:
            raise RefInUse()
        if response.status_code != 204:
            # Fail closed: without a clear yes, nothing gets deleted.
            raise PeerUnavailable(f"retire: HTTP {response.status_code}")
