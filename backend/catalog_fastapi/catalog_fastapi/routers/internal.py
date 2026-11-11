"""What `instances` may ask of `catalog`. Shapes: backend/contracts/ (#13).

The gateway never routes /internal/. Every route but health needs `instances`'
bearer token.
"""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from catalog_fastapi import events
from catalog_fastapi.auth import DbSession
from catalog_fastapi.errors import NotFound
from catalog_fastapi.peers import require_peer_token

PAGE_SIZE = 500
KINDS = {"questionnaire-types": "questionnaire_type", "battery-types": "battery_type"}

router = APIRouter()
guarded = APIRouter(dependencies=[Depends(require_peer_token)])


@router.get("/internal/health/")
def health() -> dict:
    return {"status": "ok"}


def _kind(slug: str) -> str:
    if slug not in KINDS:
        raise NotFound()
    return KINDS[slug]


@guarded.get("/internal/{slug}/")
def snapshot_list(
    slug: str,
    session: DbSession,
    after: Annotated[uuid.UUID | None, Query()] = None,
) -> dict:
    """Every type of a kind, by id, for `reconcile_refs`."""
    results = events.snapshot_page(session, _kind(slug), after=after, limit=PAGE_SIZE)
    last = results[-1]["aggregateId"] if len(results) == PAGE_SIZE else None
    return {"results": results, "next": last}


@guarded.get("/internal/{slug}/{type_id}/")
def snapshot(slug: str, type_id: uuid.UUID, session: DbSession) -> dict:
    found = events.fetch_snapshot(session, _kind(slug), type_id)
    if found is None:
        raise NotFound()
    return found
