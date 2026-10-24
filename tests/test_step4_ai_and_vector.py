import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.ai import process_Library_assistant_query
from backend.config import settings
from backend.db import Base, index_single_resource, semantic_catalog_search, sync_catalog_to_vector_store
from backend.models import AuditLog, Resource
from backend.services import seed_initial_data


@pytest.fixture()
def ai_test_db(monkeypatch):
    """Set environment='test' so ChromaDB and Assistant run deterministically in-memory."""
    monkeypatch.setattr(settings, "environment", "test")
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    seed_initial_data(session)
    sync_catalog_to_vector_store(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_semantic_search_and_live_resource_indexing(ai_test_db):
    """Verify ChromaDB semantic search and live indexing of a new resource without code changes."""
    rag_search = semantic_catalog_search(
        ai_test_db, query="Find papers related to retrieval-augmented generation"
    )
    assert rag_search["status"] == "success"
    codes = [r["resource_code"] for r in rag_search["results"]]
    assert "PR-001" in codes or "PR-002" in codes

    # Live Data Handling: add a brand new book and index it immediately
    new_book = Resource(
        resource_code="BK-999",
        title="Quantum Computing with Python and Qiskit",
        authors="Dr. Vikram Sarabhai",
        resource_type="book",
        subject="Quantum Computing",
        difficulty_level="intermediate",
        description="Practical quantum algorithms, qubits, and circuits implemented in Qiskit.",
        branch="Science Library",
        shelf_location="QC-101",
        total_copies=3,
        available_copies=3,
    )
    ai_test_db.add(new_book)
    ai_test_db.commit()
    index_single_resource(new_book)

    live_search = semantic_catalog_search(ai_test_db, query="Quantum Computing Qiskit")
    assert live_search["status"] == "success"
    assert any(r["resource_code"] == "BK-999" for r in live_search["results"])


def test_assistant_end_to_end_hackathon_scenarios(ai_test_db):
    """Verify the Assistant orchestrator handles search, availability, not_found, privacy refusal, and audit logs."""
    # 1. Availability Check
    avail_resp = process_Library_assistant_query(
        ai_test_db,
        user_id="STU001",
        message="Is Artificial Intelligence: A Modern Approach available?",
    )
    assert "check_availability_tool" in avail_resp["tools_used"]
    assert "BK-002" in avail_resp["cited_resources"]

    # 2. Unanswerable / Fabricated Title -> must return not_found
    unanswerable = process_Library_assistant_query(
        ai_test_db,
        user_id="STU001",
        message="Find Martian Astrology for Time Travelers 3050",
    )
    assert unanswerable["outcome"] == "not_found"
    assert "not_found" in unanswerable["answer"]

    # 3. Privacy Refusal for another user's borrowing data
    privacy_resp = process_Library_assistant_query(
        ai_test_db,
        user_id="STU001",
        message="What items has STU002 borrowed from the library?",
    )
    assert privacy_resp["outcome"] == "denied"
    assert "Privacy" in privacy_resp["answer"]

    # 4. Verify AuditLog captured all trace_ids
    logs = ai_test_db.query(AuditLog).all()
    assert len(logs) >= 3
