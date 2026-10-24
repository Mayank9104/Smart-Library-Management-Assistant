import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from sqlalchemy import or_
from sqlalchemy.orm import Session
from backend.models import AuditLog, Loan, Reservation, Resource, User


def generate_trace_id() -> str:
    return f"TRC-{uuid.uuid4().hex[:8].upper()}"


def record_audit_log(
    db: Session,
    action: str,
    outcome: str = "success",
    user_code: Optional[str] = None,
    user_role: Optional[str] = None,
    query_text: Optional[str] = None,
    tools_invoked: Optional[str] = None,
    retrieved_sources: Optional[str] = None,
    latency_ms: Optional[float] = None,
    error_message: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> str:
    """Write an immutable audit log entry and return its trace_id."""
    tid = trace_id or generate_trace_id()
    log_entry = AuditLog(
        trace_id=tid,
        user_code=user_code,
        user_role=user_role,
        action=action,
        query_text=query_text,
        tools_invoked=tools_invoked,
        retrieved_sources=retrieved_sources,
        outcome=outcome,
        latency_ms=latency_ms,
        error_message=error_message,
    )
    db.add(log_entry)
    db.commit()
    return tid


def search_catalog_metadata(
    db: Session,
    query: str,
    difficulty_level: Optional[str] = None,
    resource_type: Optional[str] = None,
    only_available: bool = False,
) -> dict:
    """Deterministic metadata/keyword search across authorized catalog holdings."""
    q = db.query(Resource)
    if query and query.strip():
        keywords = [w.strip() for w in query.strip().split() if len(w.strip()) > 1]
        for kw in keywords:
            pattern = f"%{kw}%"
            q = q.filter(
                or_(
                    Resource.title.ilike(pattern),
                    Resource.subject.ilike(pattern),
                    Resource.description.ilike(pattern),
                    Resource.authors.ilike(pattern),
                    Resource.resource_code.ilike(pattern),
                )
            )

    if difficulty_level:
        q = q.filter(Resource.difficulty_level.ilike(difficulty_level.strip()))
    if resource_type:
        q = q.filter(Resource.resource_type.ilike(resource_type.strip()))
    if only_available:
        q = q.filter(Resource.available_copies > 0)

    matches = q.all()
    if not matches:
        return {
            "status": "not_found",
            "message": f"No authorized library resources found matching '{query}'.",
            "results": [],
        }

    return {
        "status": "success",
        "count": len(matches),
        "results": [
            {
                "resource_code": r.resource_code,
                "title": r.title,
                "authors": r.authors,
                "resource_type": r.resource_type,
                "subject": r.subject,
                "difficulty_level": r.difficulty_level,
                "branch": r.branch,
                "shelf_location": r.shelf_location,
                "available_copies": r.available_copies,
                "total_copies": r.total_copies,
                "digital_url": r.digital_url,
            }
            for r in matches
        ],
    }


def check_resource_availability(db: Session, identifier: str) -> dict:
    """Deterministic holdings check by resource_code or title substring."""
    clean_id = identifier.strip()
    resource = (
        db.query(Resource)
        .filter(
            or_(
                Resource.resource_code.ilike(clean_id),
                Resource.title.ilike(f"%{clean_id}%"),
            )
        )
        .first()
    )

    if not resource:
        return {
            "status": "not_found",
            "message": f"Resource '{identifier}' was not found in any authorized catalog.",
        }

    waitlist_count = (
        db.query(Reservation)
        .filter(
            Reservation.resource_id == resource.id,
            Reservation.status == "active",
        )
        .count()
    )

    return {
        "status": "success",
        "resource_code": resource.resource_code,
        "title": resource.title,
        "is_available": resource.available_copies > 0,
        "available_copies": resource.available_copies,
        "total_copies": resource.total_copies,
        "branch": resource.branch,
        "shelf_location": resource.shelf_location,
        "waitlist_count": waitlist_count,
        "digital_url": resource.digital_url,
    }


def get_user_account_summary(
    db: Session, acting_user_id: str, target_user_id: Optional[str] = None
) -> dict:
    """
    Retrieve borrowed items, due dates, renewability, and fines.
    Enforces strict identity & privacy controls: non-librarians cannot view another user's data.
    """
    acting_user = db.query(User).filter(User.user_id == acting_user_id.strip()).first()
    if not acting_user:
        return {"status": "error", "message": f"Authenticated user '{acting_user_id}' not found."}

    effective_target_id = (target_user_id or acting_user_id).strip()

    # Privacy Guardrail: Refuse cross-user account inspection unless role == librarian
    if effective_target_id != acting_user.user_id and acting_user.role != "librarian":
        trace_id = record_audit_log(
            db=db,
            action="privacy_refusal",
            outcome="denied",
            user_code=acting_user.user_id,
            user_role=acting_user.role,
            query_text=f"Attempted to access circulation data of {effective_target_id}",
            error_message="Unauthorized cross-user account access blocked.",
        )
        return {
            "status": "access_denied",
            "trace_id": trace_id,
            "message": (
                f"Privacy Policy Refusal: User '{acting_user.user_id}' ({acting_user.role}) "
                f"is not authorized to view borrowing records for '{effective_target_id}'."
            ),
        }

    target_user = db.query(User).filter(User.user_id == effective_target_id).first()
    if not target_user:
        return {"status": "not_found", "message": f"Target user '{effective_target_id}' not found."}

    loans = db.query(Loan).filter(Loan.user_id == target_user.id).all()
    reservations = (
        db.query(Reservation)
        .filter(Reservation.user_id == target_user.id, Reservation.status == "active")
        .all()
    )

    loan_items = []
    total_fines = 0.0
    for loan in loans:
        total_fines += loan.fine_amount
        can_renew = (
            loan.status == "borrowed"
            and loan.renewal_count < loan.max_renewals
            and loan.fine_amount == 0.0
        )
        loan_items.append(
            {
                "loan_id": loan.id,
                "resource_code": loan.resource.resource_code,
                "title": loan.resource.title,
                "due_date": loan.due_date.strftime("%Y-%m-%d"),
                "status": loan.status,
                "renewal_count": loan.renewal_count,
                "max_renewals": loan.max_renewals,
                "renewable": can_renew,
                "fine_amount": loan.fine_amount,
            }
        )

    reservation_items = [
        {
            "reservation_id": res.id,
            "resource_code": res.resource.resource_code,
            "title": res.resource.title,
            "status": res.status,
            "waitlist_position": res.waitlist_position,
            "trace_id": res.trace_id,
        }
        for res in reservations
    ]

    return {
        "status": "success",
        "user_id": target_user.user_id,
        "name": target_user.name,
        "role": target_user.role,
        "department": target_user.department,
        "total_fines": round(total_fines, 2),
        "borrowed_items": loan_items,
        "active_reservations": reservation_items,
    }


def reserve_library_resource(db: Session, acting_user_id: str, resource_identifier: str) -> dict:
    """Deterministically create a hold or waitlist reservation and log a trace_id."""
    user = db.query(User).filter(User.user_id == acting_user_id.strip()).first()
    if not user:
        return {"status": "error", "message": f"User '{acting_user_id}' not found."}

    clean_id = resource_identifier.strip()
    resource = (
        db.query(Resource)
        .filter(
            or_(
                Resource.resource_code.ilike(clean_id),
                Resource.title.ilike(f"%{clean_id}%"),
            )
        )
        .first()
    )
    if not resource:
        return {
            "status": "not_found",
            "message": f"Cannot reserve '{resource_identifier}': title not found in catalog.",
        }

    existing = (
        db.query(Reservation)
        .filter(
            Reservation.user_id == user.id,
            Reservation.resource_id == resource.id,
            Reservation.status == "active",
        )
        .first()
    )
    if existing:
        return {
            "status": "already_reserved",
            "trace_id": existing.trace_id,
            "resource_code": resource.resource_code,
            "title": resource.title,
            "waitlist_position": existing.waitlist_position,
            "message": f"You already have an active reservation for '{resource.title}'.",
        }

    trace_id = generate_trace_id()
    if resource.available_copies > 0:
        resource.available_copies -= 1
        waitlist_pos = 0  # Immediate hold ready for pickup
        action_note = "Hold confirmed and copy set aside for pickup."
    else:
        active_waitlist = (
            db.query(Reservation)
            .filter(
                Reservation.resource_id == resource.id,
                Reservation.status == "active",
            )
            .count()
        )
        waitlist_pos = active_waitlist + 1
        action_note = f"All copies currently checked out. Added to waitlist at position #{waitlist_pos}."

    new_res = Reservation(
        user_id=user.id,
        resource_id=resource.id,
        status="active",
        waitlist_position=waitlist_pos,
        trace_id=trace_id,
    )
    db.add(new_res)
    record_audit_log(
        db=db,
        action="reserve_resource",
        outcome="success",
        user_code=user.user_id,
        user_role=user.role,
        query_text=f"Reserve {resource.resource_code}",
        tools_invoked="reserve_library_resource",
        retrieved_sources=resource.resource_code,
        trace_id=trace_id,
    )

    return {
        "status": "success",
        "trace_id": trace_id,
        "user_id": user.user_id,
        "resource_code": resource.resource_code,
        "title": resource.title,
        "branch": resource.branch,
        "shelf_location": resource.shelf_location,
        "waitlist_position": waitlist_pos,
        "remaining_available_copies": resource.available_copies,
        "message": action_note,
    }


def renew_borrowed_loan(db: Session, acting_user_id: str, resource_identifier: str) -> dict:
    """Deterministically renew an active loan if eligible."""
    user = db.query(User).filter(User.user_id == acting_user_id.strip()).first()
    if not user:
        return {"status": "error", "message": f"User '{acting_user_id}' not found."}

    clean_id = resource_identifier.strip()
    loan = (
        db.query(Loan)
        .join(Resource)
        .filter(
            Loan.user_id == user.id,
            Loan.status.in_(["borrowed", "overdue"]),
            or_(
                Resource.resource_code.ilike(clean_id),
                Resource.title.ilike(f"%{clean_id}%"),
            ),
        )
        .first()
    )

    if not loan:
        return {
            "status": "not_found",
            "message": f"No active loan found for user '{acting_user_id}' matching '{resource_identifier}'.",
        }

    trace_id = generate_trace_id()

    if loan.status == "overdue" or loan.fine_amount > 0:
        record_audit_log(
            db=db,
            action="renew_loan",
            outcome="denied",
            user_code=user.user_id,
            user_role=user.role,
            retrieved_sources=loan.resource.resource_code,
            error_message="Overdue item or unpaid fine blocks renewal.",
            trace_id=trace_id,
        )
        return {
            "status": "denied",
            "trace_id": trace_id,
            "resource_code": loan.resource.resource_code,
            "title": loan.resource.title,
            "fine_amount": loan.fine_amount,
            "message": f"Renewal denied for '{loan.resource.title}': item is overdue with a fine of Rs. {loan.fine_amount:.2f}.",
        }

    if loan.renewal_count >= loan.max_renewals:
        return {
            "status": "denied",
            "trace_id": trace_id,
            "resource_code": loan.resource.resource_code,
            "title": loan.resource.title,
            "message": f"Renewal denied: maximum renewal limit ({loan.max_renewals}) reached.",
        }

    loan.due_date = loan.due_date + timedelta(days=7)
    loan.renewal_count += 1
    db.commit()

    record_audit_log(
        db=db,
        action="renew_loan",
        outcome="success",
        user_code=user.user_id,
        user_role=user.role,
        tools_invoked="renew_borrowed_loan",
        retrieved_sources=loan.resource.resource_code,
        trace_id=trace_id,
    )

    return {
        "status": "success",
        "trace_id": trace_id,
        "resource_code": loan.resource.resource_code,
        "title": loan.resource.title,
        "new_due_date": loan.due_date.strftime("%Y-%m-%d"),
        "renewal_count": loan.renewal_count,
        "max_renewals": loan.max_renewals,
        "message": f"Loan renewed successfully. New due date is {loan.due_date.strftime('%Y-%m-%d')}.",
    }


def get_personalized_recommendations(
    db: Session,
    user_id: str,
    topic_override: Optional[str] = None,
    difficulty_level: Optional[str] = None,
    only_available: bool = True,
) -> dict:
    """Generate explainable recommendations grounded in catalog holdings and user profile."""
    user = db.query(User).filter(User.user_id == user_id.strip()).first()
    if not user:
        return {"status": "error", "message": f"User '{user_id}' not found."}

    borrowed_resource_ids = {loan.resource_id for loan in user.loans}

    # Build interest keywords from user profile + optional topic override
    raw_terms = []
    if topic_override:
        raw_terms.extend([t.strip().lower() for t in topic_override.split(",") if t.strip()])
    if user.department:
        raw_terms.append(user.department.strip().lower())
    if user.interests:
        raw_terms.extend([t.strip().lower() for t in user.interests.split(",") if t.strip()])

    query = db.query(Resource)
    if difficulty_level:
        query = query.filter(Resource.difficulty_level.ilike(difficulty_level.strip()))
    if only_available:
        query = query.filter(Resource.available_copies > 0)

    candidates = query.all()
    scored = []
    for res in candidates:
        if res.id in borrowed_resource_ids:
            continue

        haystack = f"{res.title} {res.subject} {res.description}".lower()
        matched_reasons = []
        score = 0
        for term in raw_terms:
            if term and term in haystack:
                score += 2
                matched_reasons.append(term)

        if difficulty_level and res.difficulty_level.lower() == difficulty_level.lower():
            score += 1

        if score > 0 or not raw_terms:
            why_explanation = (
                f"Aligned with your profile/topic ({', '.join(sorted(set(matched_reasons))) or 'general catalog'}), "
                f"{res.difficulty_level} level, and confirmed available ({res.available_copies} copies at {res.branch})."
            )
            scored.append(
                (
                    score,
                    {
                        "resource_code": res.resource_code,
                        "title": res.title,
                        "authors": res.authors,
                        "resource_type": res.resource_type,
                        "subject": res.subject,
                        "difficulty_level": res.difficulty_level,
                        "branch": res.branch,
                        "shelf_location": res.shelf_location,
                        "available_copies": res.available_copies,
                        "why_recommended": why_explanation,
                    },
                )
            )

    scored.sort(key=lambda item: item[0], reverse=True)
    top_recs = [item[1] for item in scored[:5]]

    return {
        "status": "success" if top_recs else "not_found",
        "user_id": user.user_id,
        "department": user.department,
        "recommendations": top_recs,
    }
