from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


# --- User Schemas ---
class UserBase(BaseModel):
    user_id: str = Field(..., description="Unique university ID like STU001 or LIB001")
    name: str
    email: EmailStr
    role: str = Field(default="student", pattern="^(student|faculty|researcher|librarian)$")
    department: Optional[str] = None
    interests: Optional[str] = None


class UserCreate(UserBase):
    pass


class UserRead(UserBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Resource Schemas ---
class ResourceBase(BaseModel):
    resource_code: str = Field(..., description="Unique catalog code like BK-001")
    title: str
    authors: str
    resource_type: str = Field(
        default="book",
        pattern="^(book|journal|paper|ebook|dissertation|digital_resource)$",
    )
    subject: str
    difficulty_level: str = Field(
        default="beginner",
        pattern="^(beginner|intermediate|advanced)$",
    )
    description: str
    publication_year: Optional[int] = None
    branch: str = "Central Library"
    shelf_location: str = "A-101"
    digital_url: Optional[str] = None
    total_copies: int = Field(default=1, ge=0)
    available_copies: int = Field(default=1, ge=0)


class ResourceCreate(ResourceBase):
    pass


class ResourceRead(ResourceBase):
    id: int
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Loan Schemas ---
class LoanRead(BaseModel):
    id: int
    user_id: int
    resource_id: int
    borrowed_at: datetime
    due_date: datetime
    returned_at: Optional[datetime] = None
    renewal_count: int
    max_renewals: int
    fine_amount: float
    status: str
    model_config = ConfigDict(from_attributes=True)


# --- Reservation Schemas ---
class ReservationCreate(BaseModel):
    acting_user_id: str = Field(..., description="Authenticated user_id making the request")
    resource_code: str = Field(..., description="Catalog resource_code to reserve")


class ReservationRead(BaseModel):
    id: int
    user_id: int
    resource_id: int
    reserved_at: datetime
    status: str
    waitlist_position: int
    trace_id: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)


# --- Audit Log Schemas ---
class AuditLogRead(BaseModel):
    id: int
    trace_id: str
    user_code: Optional[str] = None
    user_role: Optional[str] = None
    action: str
    query_text: Optional[str] = None
    tools_invoked: Optional[str] = None
    retrieved_sources: Optional[str] = None
    outcome: str
    latency_ms: Optional[float] = None
    error_message: Optional[str] = None
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)


# --- Assistant / Chat Schemas ---
class ChatRequest(BaseModel):
    user_id: str = Field(..., description="Authenticated user ID, e.g., STU001")
    message: str = Field(..., min_length=1, description="Natural language query")


class ChatResponse(BaseModel):
    trace_id: str
    answer: str
    tools_used: List[str] = Field(default_factory=list)
    cited_resources: List[str] = Field(default_factory=list)
    outcome: str = "success"
