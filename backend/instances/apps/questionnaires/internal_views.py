"""What `catalog` may ask of `instances`. See `backend/contracts/`."""

from common.peers import InternalView, RefInUse
from django.http import Http404
from rest_framework.response import Response

from . import refs


class EventView(InternalView):
    def post(self, request):
        try:
            result = refs.apply_event(request.data)
        except (KeyError, TypeError, ValueError) as exc:
            # Retrying cannot help a malformed event, so this is not a 5xx.
            return Response({"detail": str(exc)}, status=400)
        return Response({"result": result})


class RetireView(InternalView):
    def post(self, request, kind, ref_id):  # noqa: ARG002
        if kind not in refs.MODELS:
            raise Http404
        try:
            refs.retire_ref(kind, ref_id)
        except RefInUse:
            return Response({"detail": "in use"}, status=409)
        return Response(status=204)


class HealthView(InternalView):
    permission_classes = []

    def get(self, request):  # noqa: ARG002
        return Response({"status": "ok"})
