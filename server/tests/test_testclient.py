"""Проверки через fastapi.testclient.TestClient (синхронный клиент).

Маршруты ниже не обращаются к БД: ответ формируется до запроса к PostgreSQL, поэтому
синхронный TestClient не пересекается с асинхронным движком из conftest.py. Сценарии с БД
написаны на httpx.AsyncClient (см. test_gaze_api.py).
"""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_openapi_describes_business_operations():
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    assert "/sessions/{session_id}/check" in paths
    assert "/sessions/{session_id}/views" in paths
    assert "/analytics/stability-by-group" in paths


def test_validation_error_has_unified_format():
    resp = client.post("/groups", json={})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert body["detail"][0]["loc"] == ["body", "name"]


def test_unknown_route_has_unified_format():
    resp = client.get("/no-such-route")
    assert resp.status_code == 404
    assert resp.json()["code"] == "http_404"


def test_web_interface_page():
    resp = client.get("/ui/")
    assert resp.status_code == 200
    assert "VR-музей" in resp.text
