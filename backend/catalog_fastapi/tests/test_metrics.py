"""Request metrics are labelled by route template, never by URL (#9)."""

from prometheus_client import REGISTRY


def requests(handler: str, method: str, status: str) -> float:
    value = REGISTRY.get_sample_value(
        "http_requests_total", {"view": handler, "method": method, "status": status}
    )
    return value or 0


def test_handler_is_the_route_template(auth):
    created = auth.post("/api/questionnaire-types/", json={"title": "a"}).json()
    template = "/api/questionnaire-types/{type_id}/"
    before = requests(template, "GET", "200")
    auth.get(f"/api/questionnaire-types/{created['id']}/")
    assert requests(template, "GET", "200") == before + 1
    labels = {
        sample.labels.get("view")
        for metric in REGISTRY.collect()
        for sample in metric.samples
    }
    assert not any(created["id"] in (label or "") for label in labels)


def test_unknown_paths_share_one_label(client):
    before = requests("<unmatched>", "GET", "404")
    client.get("/no/such/path/123")
    assert requests("<unmatched>", "GET", "404") == before + 1
