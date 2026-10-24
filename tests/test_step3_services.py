import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.services import (
    check_resource_availability,
    get_librarian_analytics_report,
    get_personalized_recommendations,
    get_user_account_summary,
    renew_borrowed_loan,
    reserve_library_resource,
    search_catalog_metadata,
    seed_initial_data,
)


@pytest.fixture()
def seeded_db():
    """Create an isolated in-memory DB and populate it with hackathon seed data."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSession = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSession()
    seed_initial_data(session)
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_catalog_search_and_not_found_guardrail(seeded_db):
    """Verify catalog search returns citations and returns not_found for invented titles."""
    found = search_catalog_metadata(seeded_db, query="Python", difficulty_level="beginner")
    assert found["status"] == "success"
    assert any(r["resource_code"] == "BK-001" for r in found["results"])

    missing = search_catalog_metadata(seeded_db, query="Quantum Teleportation For Dragons 2099")
    assert missing["status"] == "not_found"
    assert missing["results"] == []


def test_real_time_availability_check(seeded_db):
    """Verify availability tool accurately checks copies and waitlist count."""
    avail = check_resource_availability(seeded_db, "Artificial Intelligence: A Modern Approach")
    assert avail["status"] == "success"
    assert avail["resource_code"] == "BK-002"
    assert avail["is_available"] is False
    assert avail["available_copies"] == 0
    assert avail["waitlist_count"] == 1


def test_reservation_and_renewal_workflows(seeded_db):
    """Verify deterministic reservation trace_id creation and renewal validation."""
    # Reserve an available beginner book (BK-001)
    res_result = reserve_library_resource(seeded_db, acting_user_id="STU001", resource_identifier="BK-001")
    assert res_result["status"] == "success"
    assert res_result["trace_id"].startswith("TRC-")
    assert res_result["waitlist_position"] == 0
    assert res_result["remaining_available_copies"] == 2

    # Renew an eligible active loan (BK-003 for STU001)
    renew_ok = renew_borrowed_loan(seeded_db, acting_user_id="STU001", resource_identifier="BK-003")
    assert renew_ok["status"] == "success"
    assert renew_ok["renewal_count"] == 1

    # Attempt to renew an overdue book with unpaid fine (BK-002 for STU001) -> must be denied
    renew_denied = renew_borrowed_loan(seeded_db, acting_user_id="STU001", resource_identifier="BK-002")
    assert renew_denied["status"] == "denied"


def test_privacy_refusal_for_other_users_borrowing_data(seeded_db):
    """Verify Responsible AI privacy control: STU001 cannot inspect STU002's account."""
    own_account = get_user_account_summary(seeded_db, acting_user_id="STU001", target_user_id="STU001")
    assert own_account["status"] == "success"
    assert len(own_account["borrowed_items"]) == 2

    snooping_attempt = get_user_account_summary(seeded_db, acting_user_id="STU001", target_user_id="STU002")
    assert snooping_attempt["status"] == "access_denied"
    assert snooping_attempt["trace_id"].startswith("TRC-")

    # Librarian (LIB001) IS authorized to inspect student accounts
    librarian_view = get_user_account_summary(seeded_db, acting_user_id="LIB001", target_user_id="STU002")
    assert librarian_view["status"] == "success"


def test_recommendations_and_librarian_analytics(seeded_db):
    """Verify explainable recommendations and Pandas analytics output."""
    recs = get_personalized_recommendations(seeded_db, user_id="STU001", difficulty_level="beginner")
    assert recs["status"] == "success"
    assert len(recs["recommendations"]) > 0
    assert "why_recommended" in recs["recommendations"][0]

    analytics = get_librarian_analytics_report(seeded_db)
    assert analytics["status"] == "success"
    assert analytics["kpis"]["total_catalog_titles"] == 8
    assert analytics["longest_waitlists"][0]["resource_code"] == "BK-002"
