from datetime import datetime, timezone
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship
from backend.db.database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String(50), unique=True, index=True, nullable=False)  # e.g., "STU001"
    name = Column(String(120), nullable=False)
    email = Column(String(150), unique=True, index=True, nullable=False)
    role = Column(String(30), nullable=False, default="student")  # student, faculty, researcher, librarian
    department = Column(String(100), nullable=True)  # e.g., "Computer Science", "Data Science"
    interests = Column(Text, nullable=True)  # Comma-separated topics for recommendations
    created_at = Column(DateTime, default=utc_now, nullable=False)

    loans = relationship("Loan", back_populates="user", cascade="all, delete-orphan")
    reservations = relationship("Reservation", back_populates="user", cascade="all, delete-orphan")


class Resource(Base):
    __tablename__ = "resources"

    id = Column(Integer, primary_key=True, index=True)
    resource_code = Column(String(50), unique=True, index=True, nullable=False)  # e.g., "BK-001", "PR-101"
    title = Column(String(255), nullable=False, index=True)
    authors = Column(String(255), nullable=False)
    resource_type = Column(String(50), nullable=False, default="book")  # book, journal, paper, ebook, dissertation
    subject = Column(String(100), nullable=False, index=True)
    difficulty_level = Column(String(30), nullable=False, default="beginner")  # beginner, intermediate, advanced
    description = Column(Text, nullable=False)
    publication_year = Column(Integer, nullable=True)
    branch = Column(String(100), nullable=False, default="Central Library")
    shelf_location = Column(String(60), nullable=False, default="A-101")
    digital_url = Column(String(255), nullable=True)
    total_copies = Column(Integer, nullable=False, default=1)
    available_copies = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, default=utc_now, nullable=False)

    loans = relationship("Loan", back_populates="resource", cascade="all, delete-orphan")
    reservations = relationship("Reservation", back_populates="resource", cascade="all, delete-orphan")


class Loan(Base):
    __tablename__ = "loans"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)
    borrowed_at = Column(DateTime, default=utc_now, nullable=False)
    due_date = Column(DateTime, nullable=False)
    returned_at = Column(DateTime, nullable=True)
    renewal_count = Column(Integer, nullable=False, default=0)
    max_renewals = Column(Integer, nullable=False, default=2)
    fine_amount = Column(Float, nullable=False, default=0.0)
    status = Column(String(30), nullable=False, default="borrowed")  # borrowed, returned, overdue

    user = relationship("User", back_populates="loans")
    resource = relationship("Resource", back_populates="loans")


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    resource_id = Column(Integer, ForeignKey("resources.id"), nullable=False, index=True)
    reserved_at = Column(DateTime, default=utc_now, nullable=False)
    status = Column(String(30), nullable=False, default="active")  # active, fulfilled, cancelled
    waitlist_position = Column(Integer, nullable=False, default=1)
    trace_id = Column(String(64), nullable=True, index=True)

    user = relationship("User", back_populates="reservations")
    resource = relationship("Resource", back_populates="reservations")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    trace_id = Column(String(64), unique=True, index=True, nullable=False)
    user_code = Column(String(50), nullable=True, index=True)
    user_role = Column(String(30), nullable=True)
    action = Column(String(100), nullable=False)  # e.g., "chat_query", "reserve_resource", "privacy_refusal"
    query_text = Column(Text, nullable=True)
    tools_invoked = Column(Text, nullable=True)  # JSON or comma-separated tool names
    retrieved_sources = Column(Text, nullable=True)  # Resource codes cited
    outcome = Column(String(50), nullable=False, default="success")  # success, not_found, denied, error
    latency_ms = Column(Float, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now, nullable=False)
