from fastapi.testclient import TestClient
from backend.config import settings
from backend.main import app

client = TestClient(app)


def test_api_health_and_seed(monkeypatch):
    """Verify health endpoint and database seed endpoint."""
    monkeypatch.setattr(settings, "environment", "test")
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"

    seed_resp = client.post("/api/v1/seed")
    assert seed_resp.status_code == 200
    data = seed_resp.json()
    assert data["status"] in ["seeded", "already_seeded"]


def test_api_catalog_search(monkeypatch):
    """Verify FastAPI grounded search endpoint."""
    monkeypatch.setattr(settings, "environment", "test")
    client.post("/api/v1/seed")
    resp = client.get("/api/v1/catalog/search?q=Python")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert len(data["results"]) > 0


def test_api_chat_assistant(monkeypatch):
    """Verify FastAPI chat endpoint processes student query."""
    monkeypatch.setattr(settings, "environment", "test")
    client.post("/api/v1/seed")
    payload = {
        "user_id": "STU001",
        "message": "Is Artificial Intelligence: A Modern Approach available?",
    }
    resp = client.post("/api/v1/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "trace_id" in data
    assert "answer" in data
    assert "BK-002" in data["cited_resources"]


def test_api_librarian_analytics(monkeypatch):
    """Verify FastAPI librarian analytics endpoint."""
    monkeypatch.setattr(settings, "environment", "test")
    client.post("/api/v1/seed")
    resp = client.get("/api/v1/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "success"
    assert "kpis" in data
