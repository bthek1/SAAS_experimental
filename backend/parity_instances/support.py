"""What the tests need to play `catalog`: tokens, events, snapshots, and a clock.

`catalog` issues every token and sends every type, so the suite does both itself:
tokens signed with the published dev key (which every test profile trusts, #33), and
types as `*.changed` events on `/internal/events/`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import httpx
import jwt
from common.dev_keys import DEV_SIGNING_KEY

# One per direction, as the services use them. The test profiles set these.
CATALOG_TO_INSTANCES_TOKEN = "test-catalog-to-instances"
INSTANCES_TO_CATALOG_TOKEN = "test-instances-to-catalog"

# A timestamp as DRF writes it: UTC, `Z`, microseconds when there are any.
TIMESTAMP = r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,6})?Z$"
UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"


def new_id() -> str:
    return str(uuid.uuid4())


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def token(owner_id: str, *, key=DEV_SIGNING_KEY, algorithm="RS256", **claims) -> str:
    """An access token as `catalog` issues it (simplejwt's claims)."""
    now = datetime.now(UTC)
    payload = {
        "token_type": "access",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "jti": uuid.uuid4().hex,
        "user_id": owner_id,
        **claims,
    }
    return jwt.encode(payload, key, algorithm=algorithm)


def stamp(moment: datetime | None = None) -> str:
    """How `catalog` writes a timestamp in an event: `+00:00`, microseconds."""
    moment = moment or datetime.now(UTC)
    return moment.astimezone(UTC).isoformat(timespec="microseconds")


def qtype_snapshot(
    owner_id: str,
    *,
    ref_id: str | None = None,
    version: int = 1,
    title: str = "PHQ-9",
    questionnaire_json: dict | None = None,
    created_at: str | None = None,
) -> dict:
    now = stamp()
    return {
        "type": "questionnaire_type.changed",
        "aggregateId": ref_id or new_id(),
        "version": version,
        "data": {
            "ownerId": owner_id,
            "title": title,
            "createdAt": created_at or now,
            "updatedAt": now,
            "questionnaireJson": (
                {"pages": []} if questionnaire_json is None else questionnaire_json
            ),
        },
    }


def btype_snapshot(
    owner_id: str,
    qtype_ids: list[str],
    *,
    ref_id: str | None = None,
    version: int = 1,
    title: str = "Intake",
    description: str = "",
) -> dict:
    now = stamp()
    return {
        "type": "battery_type.changed",
        "aggregateId": ref_id or new_id(),
        "version": version,
        "data": {
            "ownerId": owner_id,
            "title": title,
            "createdAt": now,
            "updatedAt": now,
            "description": description,
            "items": [
                {"questionnaireTypeId": qtype_id, "order": order}
                for order, qtype_id in enumerate(qtype_ids)
            ],
        },
    }


def as_event(snapshot: dict) -> dict:
    """A snapshot is an event without its own id."""
    return {"id": new_id(), **snapshot}


def deleted_event(kind: str, ref_id: str, owner_id: str, version: int) -> dict:
    return {
        "id": new_id(),
        "type": f"{kind}.deleted",
        "aggregateId": ref_id,
        "version": version,
        "data": {"ownerId": owner_id},
    }


def user_event(action: str, owner_id: str, version: int) -> dict:
    return {
        "id": new_id(),
        "type": f"user.{action}",
        "aggregateId": owner_id,
        "version": version,
        "data": {},
    }


@dataclass
class Owner:
    id: str
    http: httpx.Client


class Catalog:
    """Sends what `catalog` sends, on the inbound peer token."""

    def __init__(self, http: httpx.Client) -> None:
        self.http = http

    def send(self, event: dict) -> httpx.Response:
        return self.http.post("/internal/events/", json=event)

    def apply(self, event: dict) -> str:
        response = self.send(event)
        assert response.status_code == 200, response.text
        return response.json()["result"]

    def qtype(self, owner: Owner | str, **fields) -> dict:
        owner_id = owner if isinstance(owner, str) else owner.id
        snapshot = qtype_snapshot(owner_id, **fields)
        assert self.apply(as_event(snapshot)) == "applied"
        return snapshot

    def btype(self, owner: Owner | str, qtype_ids: list[str], **fields) -> dict:
        owner_id = owner if isinstance(owner, str) else owner.id
        snapshot = btype_snapshot(owner_id, qtype_ids, **fields)
        assert self.apply(as_event(snapshot)) == "applied"
        return snapshot

    def retire(self, kind: str, ref_id: str) -> httpx.Response:
        return self.http.post(f"/internal/refs/{kind}/{ref_id}/retire/")


def create_questionnaire(owner: Owner, qtype_id: str, **body) -> dict:
    response = owner.http.post(
        "/api/questionnaires/", json={"questionnaireTypeId": qtype_id, **body}
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_battery(owner: Owner, btype_id: str, **body) -> dict:
    response = owner.http.post(
        "/api/batteries/", json={"batteryTypeId": btype_id, **body}
    )
    assert response.status_code == 201, response.text
    return response.json()


def submit(http: httpx.Client, share_token: str, answers=None, metrics=None):
    body = {"answers": answers or {}}
    if metrics is not None:
        body["metrics"] = metrics
    return http.patch(f"/api/questionnaires/by-token/{share_token}/submit/", json=body)


class Clock:
    """Moves rows in time, which no endpoint can do.

    A plain UPDATE of the two timestamps the dashboards read, on the schema Django
    built and `instances` keeps (#42). Run with the cache off, since nothing tells the
    service the rows changed.
    """

    def __init__(self, database: str) -> None:
        self.database = database

    def set(
        self,
        questionnaire_id: str,
        *,
        created_at: datetime | None = None,
        submitted_at: datetime | None = None,
    ) -> None:
        import psycopg

        values = {"created_at": created_at, "submitted_at": submitted_at}
        values = {column: value for column, value in values.items() if value}
        assignments = ", ".join(f"{column} = %s" for column in values)
        with psycopg.connect(self.database) as connection:
            cursor = connection.execute(
                f"UPDATE questionnaires_questionnaire SET {assignments} WHERE id = %s",  # noqa: S608 (fixed column names)
                [*values.values(), questionnaire_id],
            )
            assert cursor.rowcount == 1
