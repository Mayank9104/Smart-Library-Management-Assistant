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


def test_signup_signin_and_persisted_reservation(monkeypatch):
    """Verify creating a new account, signing in, reserving a book, and seeing it in Account Summary."""
    monkeypatch.setattr(settings, "environment", "test")
    client.post("/api/v1/seed")

    # 1. Sign Up new student account
    signup_resp = client.post(
        "/api/v1/auth/signup",
        json={
            "user_id": "STU099",
            "name": "Test Student",
            "email": "stu099@university.edu",
            "password": "secretpassword",
            "role": "student",
            "department": "Data Science",
            "interests": "Python, AI",
        },
    )
    assert signup_resp.status_code == 200
    token = signup_resp.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Sign In with newly created account
    signin_resp = client.post(
        "/api/v1/auth/signin",
        json={"identifier": "STU099", "password": "secretpassword"},
    )
    assert signin_resp.status_code == 200
    assert signin_resp.json()["user"]["user_id"] == "STU099"

    # 3. Reserve a resource (BK-002) using Bearer token
    res_resp = client.post(
        "/api/v1/circulation/reserve",
        json={"resource_code": "BK-002"},
        headers=headers,
    )
    assert res_resp.status_code == 200
    assert res_resp.json()["status"] == "success"

    # 4. Verify reservation is persisted in Account Summary
    acc_resp = client.get("/api/v1/account/STU099", headers=headers)
    assert acc_resp.status_code == 200
    acc_data = acc_resp.json()
    assert acc_data["status"] == "success"
    reserved_codes = [r["resource_code"] for r in acc_data["active_reservations"]]
    assert "BK-002" in reserved_codes


def test_librarian_admin_rbac_security(monkeypatch):
    """Verify students are blocked (403) from admin endpoints while librarians succeed (200)."""
    monkeypatch.setattr(settings, "environment", "test")
    client.post("/api/v1/seed")

    # Student login
    stu_login = client.post(
        "/api/v1/auth/signin",
        json={"identifier": "STU001", "password": "pass123"},
    )
    stu_headers = {"Authorization": f"Bearer {stu_login.json()['access_token']}"}

    # Student blocked from adding catalog resources
    forbidden_resp = client.post(
        "/api/v1/admin/resources",
        json={
            "resource_code": "BK-777",
            "title": "Unauthorized Book",
            "authors": "Anon",
        },
        headers=stu_headers,
    )
    assert forbidden_resp.status_code == 403

    # Librarian login
    lib_login = client.post(
        "/api/v1/auth/signin",
        json={"identifier": "LIB001", "password": "pass123"},
    )
    lib_headers = {"Authorization": f"Bearer {lib_login.json()['access_token']}"}

    # Librarian allowed to add new resource and index live
    allowed_resp = client.post(
        "/api/v1/admin/resources",
        json={
            "resource_code": "BK-888",
            "title": "Enterprise RAG Systems",
            "authors": "Dr. A. Gangwar",
            "resource_type": "book",
            "subject": "Artificial Intelligence",
            "difficulty_level": "advanced",
        },
        headers=lib_headers,
    )
    assert allowed_resp.status_code == 200
    assert allowed_resp.json()["status"] == "success"
