"""What `instances` may ask of `catalog`. See `backend/contracts/`."""

from common.peers import InternalView
from django.http import Http404
from rest_framework.response import Response

from . import events

PAGE_SIZE = 500


class TypeSnapshotView(InternalView):
    kind: str = ""

    def get(self, request, type_id):  # noqa: ARG002
        snapshot = events.fetch_snapshot(self.kind, type_id)
        if snapshot is None:
            raise Http404
        return Response(snapshot)


class TypeSnapshotListView(InternalView):
    """Every type of a kind, by id, for `reconcile_refs`."""

    kind: str = ""

    def get(self, request):
        results = events.snapshot_page(
            self.kind, after=request.query_params.get("after"), limit=PAGE_SIZE
        )
        last = results[-1]["aggregateId"] if len(results) == PAGE_SIZE else None
        return Response({"results": results, "next": last})


class HealthView(InternalView):
    permission_classes = []

    def get(self, request):  # noqa: ARG002
        return Response({"status": "ok"})
