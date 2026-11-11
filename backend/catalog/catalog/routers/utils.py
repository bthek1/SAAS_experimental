"""Health, and the Celery demo the SPA's task panel drives. All public."""

from typing import Annotated, Any

from celery.result import AsyncResult
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from catalog.celery_app import app as celery_app
from catalog.celery_app import process_data
from catalog.errors import json_body

router = APIRouter()
Body = Annotated[Any, Depends(json_body)]


@router.get("/api/health/")
def health() -> dict:
    return {"status": "ok"}


@router.post("/api/tasks/trigger/")
def task_trigger(body: Body) -> JSONResponse:
    payload = body if isinstance(body, dict) else {}
    task = process_data.delay(payload)
    return JSONResponse({"task_id": task.id}, status_code=202)


@router.get("/api/tasks/{task_id}/")
def task_status(task_id: str) -> dict:
    result = AsyncResult(task_id, app=celery_app)
    data: dict = {
        "task_id": task_id,
        "status": result.status,
        "result": None,
        "traceback": None,
    }
    if result.successful():
        data["result"] = result.result
    elif result.failed():
        data["traceback"] = str(result.traceback)
    return data


@router.post("/api/tasks/{task_id}/revoke/")
def task_revoke(task_id: str, body: Body) -> dict:
    terminate = bool(body.get("terminate", False)) if isinstance(body, dict) else False
    AsyncResult(task_id, app=celery_app).revoke(terminate=terminate)
    return {"task_id": task_id, "revoked": True}
