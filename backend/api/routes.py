from datetime import datetime, timedelta
from typing import Any, Dict, Optional
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from backend.db import (
    get_db,
    index_single_resource,
    init_db,
    sync_catalog_to_vector_store,
)
from backend.models import Loan, Reservation, Resource, User
from backend.schemas import ChatRequest, ChatResponse
import backend.services as lib_services
from backend.services import (
    get_librarian_analytics_report,
    seed_initial_data,
)
from backend.services.auth_service import (
    authenticate_user,
    register_user,
    verify_access_token,
)
from backend.db.vector_store import semantic_catalog_search
from backend.ai import process_Library_assistant_query

router = APIRouter(prefix="/api/v1", tags=["Library API"])


# --- Auth & Action Request Schemas ---
class SignUpRequest(BaseModel):
    user_id: str = Field(..., examples=["STU005"])
    name: str = Field(..., examples=["Rohan Sharma"])
    email: str = Field(..., examples=["rohan@university.edu"])
    password: str = Field(..., min_length=4, examples=["pass123"])
    role: str = Field(default="student", examples=["student"])
    department: str = Field(default="Computer Science")
    interests: str = Field(default="Machine Learning, Python, Data Science")


class SignInRequest(BaseModel):
    identifier: str = Field(..., description="User ID (e.g. STU001) or Email")
    password: str = Field(..., description="Password (default demo: pass123)")


class CirculationActionRequest(BaseModel):
    user_id: Optional[str] = None
    resource_code: str = Field(..., examples=["BK-002"])


class AdminCreateResourceRequest(BaseModel):
    resource_code: str = Field(..., examples=["BK-099"])
    title: str = Field(..., examples=["Designing Data-Intensive Applications"])
    authors: str = Field(..., examples=["Martin Kleppmann"])
    resource_type: str = Field(default="book", examples=["book"])
    subject: str = Field(default="Data Engineering", examples=["Data Engineering"])
    difficulty_level: str = Field(default="intermediate", examples=["intermediate"])
    branch: str = Field(default="Central Library")
    shelf_location: str = Field(default="CS-402")
    total_copies: int = Field(default=3, ge=1)
    available_copies: int = Field(default=3, ge=0)
    description: Optional[str] = Field(default="Comprehensive guide to reliable, scalable systems.")


def _ensure_seeded(db: Session) -> None:
    """Ensure SQLite tables exist and initial seed data is loaded."""
    init_db()
    if db.query(User).count() == 0:
        seed_initial_data(db)
        sync_catalog_to_vector_store(db)


def get_optional_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Resolve the authenticated User from Bearer token if provided."""
    _ensure_seeded(db)
    if not authorization or not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    payload = verify_access_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired authentication token.")
    user = db.query(User).filter(User.user_id == payload["user_id"]).first()
    if not user:
        raise HTTPException(status_code=401, detail="Authenticated user not found.")
    return user


def require_librarian_admin(
    current_user: Optional[User] = Depends(get_optional_current_user),
) -> User:
    """Strict RBAC dependency: Only authenticated librarians can execute admin controls."""
    if not current_user:
        raise HTTPException(
            status_code=401,
            detail="Authentication required. Sign in as a Librarian (e.g., LIB001) to access admin controls.",
        )
    if current_user.role.lower() != "librarian":
        raise HTTPException(
            status_code=403,
            detail=f"Access Denied: Role '{current_user.role}' cannot access Librarian Admin Controls.",
        )
    return current_user


# --- 1. Authentication Endpoints (Sign Up, Sign In, Current User, Demo Users) ---
@router.post("/auth/signup", summary="Create a new user account")
def signup_endpoint(payload: SignUpRequest, db: Session = Depends(get_db)) -> dict:
    """Register a new student, faculty, researcher, or librarian account."""
    _ensure_seeded(db)
    result = register_user(
        db=db,
        user_id=payload.user_id,
        name=payload.name,
        email=payload.email,
        password=payload.password,
        role=payload.role,
        department=payload.department,
        interests=payload.interests,
    )
    if result["status"] == "error":
        raise HTTPException(status_code=400, detail=result["message"])
    return result


@router.post("/auth/signin", summary="Sign in with User ID or Email")
def signin_endpoint(payload: SignInRequest, db: Session = Depends(get_db)) -> dict:
    """Authenticate user credentials and return a signed Bearer token."""
    _ensure_seeded(db)
    result = authenticate_user(db=db, identifier=payload.identifier, password=payload.password)
    if result["status"] == "error":
        raise HTTPException(status_code=401, detail=result["message"])
    return result


@router.get("/auth/me", summary="Get currently authenticated user profile")
def get_me(current_user: Optional[User] = Depends(get_optional_current_user)) -> dict:
    """Verify token and return active user profile."""
    if not current_user:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return {
        "status": "success",
        "user": {
            "user_id": current_user.user_id,
            "name": current_user.name,
            "email": current_user.email,
            "role": current_user.role,
            "department": current_user.department,
            "interests": current_user.interests,
        },
    }


@router.get("/auth/users", summary="List registered users for quick demo switching")
def list_registered_users(db: Session = Depends(get_db)) -> dict:
    """Return registered user IDs, names, and roles."""
    _ensure_seeded(db)
    users = db.query(User).order_by(User.id.asc()).all()
    return {
        "status": "success",
        "users": [
            {
                "user_id": u.user_id,
                "name": u.name,
                "email": u.email,
                "role": u.role,
                "department": u.department,
                "interests": u.interests,
            }
            for u in users
        ],
    }


# --- 2. Core Seed, Chat & Discovery Endpoints ---
@router.post("/seed", summary="Seed initial library data")
def seed_database(db: Session = Depends(get_db)) -> dict:
    """Populate database with sample users, catalog resources, and loans."""
    init_db()
    result = seed_initial_data(db)
    sync_catalog_to_vector_store(db)
    return result


@router.post("/chat", response_model=ChatResponse, summary="Process AI Assistant Chat Query")
def chat_with_assistant(
    payload: ChatRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> ChatResponse:
    """Send a natural-language query to the AI Smart Library Assistant."""
    _ensure_seeded(db)
    effective_user_id = current_user.user_id if current_user else payload.user_id
    response = process_Library_assistant_query(
        db=db, user_id=effective_user_id, message=payload.message
    )
    return ChatResponse(**response)


@router.get("/catalog/search", summary="Grounded Semantic Catalog Search")
def search_catalog(
    q: str = Query(..., description="Search query"),
    difficulty: Optional[str] = Query(None, description="beginner, intermediate, advanced"),
    resource_type: Optional[str] = Query(None, description="book, paper, ebook, dissertation"),
    db: Session = Depends(get_db),
) -> dict:
    """Search catalog items using semantic vector search and SQLite holdings."""
    _ensure_seeded(db)
    return semantic_catalog_search(
        db=db, query=q, difficulty_level=difficulty, resource_type=resource_type
    )


# --- 3. Account Summary, Direct Reservation & Direct Renewal Endpoints ---
@router.get("/account/{target_user_id}", summary="Get structured account loans and reservations")
def get_account_details(
    target_user_id: str,
    requester_id: Optional[str] = Query(None, description="Fallback requester user_id if no Bearer token"),
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Return structured loans, reservations, and fines with strict privacy enforcement."""
    _ensure_seeded(db)
    effective_requester = (
        current_user.user_id if current_user else (requester_id or target_user_id)
    ).upper()
    target_uid = target_user_id.strip().upper()

    requester = db.query(User).filter(User.user_id == effective_requester).first()
    if not requester:
        return {"status": "error", "message": f"Requester '{effective_requester}' not found."}

    # Enforce strict privacy guardrail: only self or librarian can view account data
    if effective_requester != target_uid and requester.role.lower() != "librarian":
        return {
            "status": "privacy_refusal",
            "message": (
                f"Privacy policy refusal: User '{effective_requester}' ({requester.role}) is not "
                f"authorized to access borrowing or reservation records for '{target_uid}'."
            ),
        }

    target_user = db.query(User).filter(User.user_id == target_uid).first()
    if not target_user:
        return {"status": "not_found", "message": f"User '{target_uid}' not found."}

    loans = db.query(Loan).filter(Loan.user_id == target_user.id).all()
    active_loans = []
    for loan in loans:
        res = db.query(Resource).filter(Resource.id == loan.resource_id).first()
        active_loans.append({
            "loan_id": loan.id,
            "resource_code": res.resource_code if res else str(loan.resource_id),
            "title": res.title if res else "Unknown Title",
            "due_date": str(loan.due_date),
            "status": loan.status,
            "renewals_used": getattr(loan, "renewals_used", 0),
            "max_renewals": getattr(loan, "max_renewals", 2),
            "fine_amount": float(getattr(loan, "fine_amount", 0.0) or 0.0),
        })

    reservations = db.query(Reservation).filter(Reservation.user_id == target_user.id).all()
    active_reservations = []
    for r in reservations:
        res = db.query(Resource).filter(Resource.id == r.resource_id).first()
        active_reservations.append({
            "reservation_id": r.id,
            "resource_code": res.resource_code if res else str(r.resource_id),
            "title": res.title if res else "Unknown Title",
            "branch": res.branch if res else "Central Library",
            "shelf_location": res.shelf_location if res else "N/A",
            "status": r.status,
            "queue_position": getattr(r, "queue_position", 1),
        })

    return {
        "status": "success",
        "user": {
            "user_id": target_user.user_id,
            "name": target_user.name,
            "email": target_user.email,
            "role": target_user.role,
            "department": target_user.department,
        },
        "active_loans": active_loans,
        "active_reservations": active_reservations,
    }


@router.post("/circulation/reserve", summary="Reserve a catalog resource and persist to account")
def reserve_resource_endpoint(
    payload: CirculationActionRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Create a hold/reservation on a book or resource and save it to SQLite."""
    _ensure_seeded(db)
    effective_user_id = (current_user.user_id if current_user else payload.user_id or "").strip().upper()
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="User authentication required to reserve a resource.")

    code = payload.resource_code.strip().upper()
    user = db.query(User).filter(User.user_id == effective_user_id).first()
    if not user:
        return {"status": "error", "message": f"User '{effective_user_id}' not found."}

    resource = db.query(Resource).filter(Resource.resource_code == code).first()
    if not resource:
        return {"status": "not_found", "message": f"Resource '{code}' not found in catalog."}

    # Check if user already has an active reservation for this resource
    existing_res = (
        db.query(Reservation)
        .filter(
            Reservation.user_id == user.id,
            Reservation.resource_id == resource.id,
            Reservation.status.in_(["active", "ready_for_pickup", "waitlisted", "pending"]),
        )
        .first()
    )
    if existing_res:
        return {
            "status": "success",
            "message": f"You already have an active reservation for [{code}] '{resource.title}' (Status: {existing_res.status}).",
            "reservation_id": existing_res.id,
            "resource_code": code,
        }

    queue_count = db.query(Reservation).filter(Reservation.resource_id == resource.id).count()
    if resource.available_copies > 0:
        resource.available_copies -= 1
        res_status = "ready_for_pickup"
    else:
        res_status = "waitlisted"

    new_reservation = Reservation(
        user_id=user.id,
        resource_id=resource.id,
        status=res_status,
    )
    if hasattr(new_reservation, "queue_position"):
        setattr(new_reservation, "queue_position", queue_count + 1)

    db.add(new_reservation)
    db.commit()
    db.refresh(new_reservation)

    return {
        "status": "success",
        "message": (
            f"Reserved [{code}] '{resource.title}' for {user.name} ({user.user_id}). "
            f"Status: {res_status.upper()} | Location: {resource.branch} ({resource.shelf_location})."
        ),
        "reservation_id": new_reservation.id,
        "resource_code": code,
        "reservation_status": res_status,
    }


@router.post("/circulation/renew", summary="Renew an active loan")
def renew_resource_endpoint(
    payload: CirculationActionRequest,
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Renew an active borrowed item for the authenticated user."""
    _ensure_seeded(db)
    effective_user_id = (current_user.user_id if current_user else payload.user_id or "").strip().upper()
    if not effective_user_id:
        raise HTTPException(status_code=401, detail="User authentication required to renew a loan.")

    code = payload.resource_code.strip().upper()
    # Try existing service function if present
    service_fn = getattr(lib_services, "renew_loan", None) or getattr(lib_services, "renew_user_loan", None)
    if service_fn:
        try:
            return service_fn(db=db, user_id=effective_user_id, resource_code=code)
        except TypeError:
            pass

    user = db.query(User).filter(User.user_id == effective_user_id).first()
    resource = db.query(Resource).filter(Resource.resource_code == code).first()
    if not user or not resource:
        return {"status": "not_found", "message": "User or resource not found."}

    loan = (
        db.query(Loan)
        .filter(Loan.user_id == user.id, Loan.resource_id == resource.id)
        .first()
    )
    if not loan:
        return {"status": "not_found", "message": f"No active loan found for {code}."}

    if loan.status == "overdue" or getattr(loan, "fine_amount", 0.0) > 0:
        return {
            "status": "denied",
            "message": f"Cannot renew [{code}] because the loan is overdue or has unpaid fines.",
        }

    max_ren = getattr(loan, "max_renewals", 2)
    if loan.renewals_used >= max_ren:
        return {
            "status": "denied",
            "message": f"Maximum renewals ({max_ren}) already reached for [{code}].",
        }

    loan.renewals_used += 1
    if isinstance(loan.due_date, datetime):
        loan.due_date = loan.due_date + timedelta(days=14)
    db.commit()
    db.refresh(loan)

    return {
        "status": "success",
        "message": f"Loan for [{code}] '{resource.title}' renewed! New due date: {loan.due_date}.",
        "resource_code": code,
        "renewals_used": loan.renewals_used,
    }


# --- 4. Analytics & Librarian Admin Control Endpoints (Secured by RBAC) ---
@router.get("/analytics", summary="Librarian Circulation & Demand Analytics")
def get_analytics(
    current_user: Optional[User] = Depends(get_optional_current_user),
    db: Session = Depends(get_db),
) -> dict:
    """Retrieve Pandas-powered analytics (enforces librarian role when Bearer token is present)."""
    _ensure_seeded(db)
    if current_user and current_user.role.lower() != "librarian":
        raise HTTPException(
            status_code=403,
            detail="Access Denied: Only users with the 'librarian' role can view library analytics.",
        )
    return get_librarian_analytics_report(db=db)


@router.post("/admin/resources", summary="[Librarian Admin] Add new resource & index live into ChromaDB")
def admin_add_resource(
    payload: AdminCreateResourceRequest,
    admin_user: User = Depends(require_librarian_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Allow a librarian to add or update a resource and immediately index it in ChromaDB."""
    code = payload.resource_code.strip().upper()
    existing = db.query(Resource).filter(Resource.resource_code == code).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"Resource code '{code}' already exists.")

    new_res = Resource(
        resource_code=code,
        title=payload.title.strip(),
        authors=payload.authors.strip(),
        resource_type=payload.resource_type.lower(),
        subject=payload.subject.strip(),
        difficulty_level=payload.difficulty_level.lower(),
        branch=payload.branch.strip(),
        shelf_location=payload.shelf_location.strip(),
        total_copies=payload.total_copies,
        available_copies=payload.available_copies,
    )
    if hasattr(new_res, "description"):
        setattr(new_res, "description", payload.description)
    elif hasattr(new_res, "summary"):
        setattr(new_res, "summary", payload.description)

    db.add(new_res)
    db.commit()
    db.refresh(new_res)

    # Live vector indexing without code changes
    index_single_resource(new_res)

    return {
        "status": "success",
        "message": f"Resource [{new_res.resource_code}] '{new_res.title}' added by Librarian {admin_user.name} and indexed live.",
        "resource": {
            "resource_code": new_res.resource_code,
            "title": new_res.title,
            "authors": new_res.authors,
            "available_copies": new_res.available_copies,
            "total_copies": new_res.total_copies,
        },
    }


@router.get("/admin/circulation", summary="[Librarian Admin] View all system loans, reservations & users")
def admin_view_all_circulation(
    admin_user: User = Depends(require_librarian_admin),
    db: Session = Depends(get_db),
) -> dict:
    """Return complete circulation ledger across all users for Librarian Admin oversight."""
    loans = db.query(Loan).all()
    reservations = db.query(Reservation).all()

    loan_list = []
    for loan in loans:
        user = db.query(User).filter(User.id == loan.user_id).first()
        res = db.query(Resource).filter(Resource.id == loan.resource_id).first()
        loan_list.append({
            "loan_id": loan.id,
            "user_id": user.user_id if user else str(loan.user_id),
            "user_name": user.name if user else "Unknown",
            "resource_code": res.resource_code if res else str(loan.resource_id),
            "title": res.title if res else "Unknown",
            "due_date": str(loan.due_date),
            "status": loan.status,
            "renewals_used": loan.renewals_used,
            "fine_amount": loan.fine_amount,
        })

    res_list = []
    for r in reservations:
        user = db.query(User).filter(User.id == r.user_id).first()
        res = db.query(Resource).filter(Resource.id == r.resource_id).first()
        res_list.append({
            "reservation_id": r.id,
            "user_id": user.user_id if user else str(r.user_id),
            "user_name": user.name if user else "Unknown",
            "resource_code": res.resource_code if res else str(r.resource_id),
            "title": res.title if res else "Unknown",
            "status": r.status,
            "queue_position": getattr(r, "queue_position", 1),
        })

    return {
        "status": "success",
        "admin": admin_user.user_id,
        "loans": loan_list,
        "reservations": res_list,
    }
