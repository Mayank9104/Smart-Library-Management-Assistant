from datetime import datetime, timedelta, timezone
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.db.database import Base
from backend.models import AuditLog, Loan, Reservation, Resource, User
from backend.schemas import ResourceCreate, ResourceRead, UserCreate, UserRead


@pytest.fixture()
def db_session():
    """Use an isolated in-memory SQLite database for fast, repeatable unit tests."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_user_and_resource_orm_and_schema(db_session):
    """Verify ORM persistence and conversion into Pydantic Read schemas."""
    user_in = UserCreate(
        user_id="STU001",
        name="Aarav Sharma",
        email="aarav@university.edu",
        role="student",
        department="Data Science",
        interests="machine learning, python, generative ai",
    )
    db_user = User(**user_in.model_dump())
    db_session.add(db_user)

    resource_in = ResourceCreate(
        resource_code="BK-101",
        title="Python Machine Learning for Beginners",
        authors="Sebastian Raschka",
        resource_type="book",
        subject="Machine Learning",
        difficulty_level="beginner",
        description="A beginner-friendly introduction to machine learning with Python.",
        publication_year=2024,
        branch="Central Library",
        shelf_location="CS-204",
        total_copies=3,
        available_copies=2,
    )
    db_resource = Resource(**resource_in.model_dump())
    db_session.add(db_resource)
    db_session.commit()
    db_session.refresh(db_user)
    db_session.refresh(db_resource)

    # Validate conversion to Pydantic Read schemas
    user_out = UserRead.model_validate(db_user)
    resource_out = ResourceRead.model_validate(db_resource)

    assert user_out.user_id == "STU001"
    assert user_out.role == "student"
    assert resource_out.resource_code == "BK-101"
    assert resource_out.available_copies == 2


def test_loan_reservation_and_audit_log_relationships(db_session):
    """Verify Loans, Reservations, and AuditLog tables work with foreign keys."""
    user = User(
        user_id="STU002",
        name="Priya Nair",
        email="priya@university.edu",
        role="researcher",
    )
    resource = Resource(
        resource_code="PR-201",
        title="Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks",
        authors="Patrick Lewis et al.",
        resource_type="paper",
        subject="Artificial Intelligence",
        difficulty_level="advanced",
        description="Foundational research paper on RAG systems.",
        total_copies=1,
        available_copies=0,
    )
    db_session.add_all([user, resource])
    db_session.commit()

    loan = Loan(
        user_id=user.id,
        resource_id=resource.id,
        due_date=datetime.now(timezone.utc) + timedelta(days=7),
        fine_amount=0.0,
        status="borrowed",
    )
    reservation = Reservation(
        user_id=user.id,
        resource_id=resource.id,
        status="active",
        waitlist_position=1,
        trace_id="TRC-TEST-001",
    )
    audit = AuditLog(
        trace_id="TRC-TEST-001",
        user_code="STU002",
        user_role="researcher",
        action="reserve_resource",
        tools_invoked="reserve_resource_tool",
        retrieved_sources="PR-201",
        outcome="success",
        latency_ms=42.5,
    )
    db_session.add_all([loan, reservation, audit])
    db_session.commit()

    assert len(user.loans) == 1
    assert user.loans[0].resource.resource_code == "PR-201"
    assert len(resource.reservations) == 1
    assert db_session.query(AuditLog).filter_by(trace_id="TRC-TEST-001").first() is not None


def test_schema_rejects_invalid_role():
    """Verify Pydantic schema validation blocks invalid user roles."""
    with pytest.raises(ValidationError):
        UserCreate(
            user_id="BAD001",
            name="Invalid Role User",
            email="bad@university.edu",
            role="hacker",  # Must be student, faculty, researcher, or librarian
        )
