"""How `instances` reaches `catalog` over HTTP (#13)."""

from collections.abc import Iterator

from common.peers import PeerUnavailable, peer_request
from django.conf import settings

SLUGS = {"questionnaire_type": "questionnaire-types", "battery_type": "battery-types"}


class HttpCatalog:
    def fetch(self, kind: str, ref_id) -> dict | None:
        response = peer_request(
            "GET", settings.CATALOG_INTERNAL_URL, f"/internal/{SLUGS[kind]}/{ref_id}/"
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise PeerUnavailable(f"fetch: HTTP {response.status_code}")
        return response.json()

    def iter_snapshots(self, kind: str) -> Iterator[dict]:
        after = None
        while True:
            params = {"after": after} if after else {}
            response = peer_request(
                "GET",
                settings.CATALOG_INTERNAL_URL,
                f"/internal/{SLUGS[kind]}/",
                params=params,
            )
            if response.status_code != 200:
                raise PeerUnavailable(f"list: HTTP {response.status_code}")
            page = response.json()
            yield from page["results"]
            after = page["next"]
            if after is None:
                return
