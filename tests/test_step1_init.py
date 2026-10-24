from pathlib import Path
from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)


def test_required_directories_exist():
    """Verify all required architectural directories exist."""
    root = Path(__file__).resolve().parent.parent
    required_dirs = [
        "frontend",
        "backend",
        "backend/api",
        "backend/services",
        "backend/models",
        "backend/schemas",
        "backend/db",
        "backend/ai",
        "backend/tools",
        "data",
        "tests",
    ]
    for dir_path in required_dirs:
        assert (root / dir_path).is_dir(), f"Missing directory: {dir_path}"


def test_health_endpoint():
    """Verify FastAPI /health endpoint responds with Groq/Local config details."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["llm_provider"] in ["groq", "local"]
    assert "active_model" in data
    assert "embedding_model" in data
