from fastapi.testclient import TestClient

from app import main

client = TestClient(main.app)


def test_health_ok_when_db_reachable(monkeypatch):
    monkeypatch.setattr(main, "_db_ok", lambda: True)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["db"] is True


def test_health_503_when_db_down(monkeypatch):
    monkeypatch.setattr(main, "_db_ok", lambda: False)
    resp = client.get("/api/health")
    assert resp.status_code == 503
    assert resp.json()["status"] == "degraded"
