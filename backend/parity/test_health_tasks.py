"""Health and the Celery demo endpoints. Tasks run eagerly under the suite."""


def test_health(client):
    response = client.get("/api/health/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_trigger_returns_a_task_id(client):
    response = client.post("/api/tasks/trigger/", json={"a": 1})
    assert response.status_code == 202
    body = response.json()
    assert set(body) == {"task_id"}
    assert isinstance(body["task_id"], str)


def test_status_shape(client):
    task_id = client.post("/api/tasks/trigger/", json={}).json()["task_id"]
    response = client.get(f"/api/tasks/{task_id}/")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"task_id", "status", "result", "traceback"}
    assert body["task_id"] == task_id
    assert body["status"] in {"PENDING", "STARTED", "SUCCESS", "FAILURE", "RETRY"}


def test_unknown_task_is_pending(client):
    body = client.get("/api/tasks/no-such-task/").json()
    assert body == {
        "task_id": "no-such-task",
        "status": "PENDING",
        "result": None,
        "traceback": None,
    }


def test_revoke(client):
    response = client.post("/api/tasks/some-task/revoke/", json={"terminate": False})
    assert response.status_code == 200
    assert response.json() == {"task_id": "some-task", "revoked": True}


def test_tasks_need_no_token(client):
    assert "Authorization" not in client.headers
    assert client.get("/api/tasks/x/").status_code == 200
