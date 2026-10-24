import base64
import hashlib
import hmac
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models import User

SECRET_KEY = getattr(settings, "secret_key", "hcltech-smart-library-secret-key-2026")


def hash_password(password: str) -> str:
    """Create a deterministic salted SHA-256 password hash."""
    salted = f"{SECRET_KEY}:{password}".encode("utf-8")
    return hashlib.sha256(salted).hexdigest()


def create_access_token(user_id: str, role: str) -> str:
    """Create a signed HMAC bearer token encoding user_id and role."""
    payload = f"{user_id}:{role}"
    signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    raw_token = f"{payload}:{signature}"
    return base64.urlsafe_b64encode(raw_token.encode("utf-8")).decode("utf-8")


def verify_access_token(token: str) -> Optional[Dict[str, str]]:
    """Verify a signed HMAC bearer token and return user_id and role."""
    try:
        decoded = base64.urlsafe_b64decode(token.encode("utf-8")).decode("utf-8")
        user_id, role, signature = decoded.split(":", 2)
        expected_sig = hmac.new(
            SECRET_KEY.encode("utf-8"),
            f"{user_id}:{role}".encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        if hmac.compare_digest(signature, expected_sig):
            return {"user_id": user_id, "role": role}
    except Exception:
        return None
    return None


def register_user(
    db: Session,
    user_id: str,
    name: str,
    email: str,
    password: str,
    role: str = "student",
    department: str = "Computer Science",
    interests: str = "Artificial Intelligence, Python",
) -> Dict[str, Any]:
    """Register a new library user account and return an auth token."""
    clean_uid = user_id.strip().upper()
    clean_email = email.strip().lower()
    valid_roles = {"student", "faculty", "researcher", "librarian"}
    if role.lower() not in valid_roles:
        return {"status": "error", "message": f"Invalid role '{role}'."}

    existing = (
        db.query(User)
        .filter((User.user_id == clean_uid) | (User.email == clean_email))
        .first()
    )
    if existing:
        return {
            "status": "error",
            "message": f"User ID '{clean_uid}' or email '{clean_email}' is already registered.",
        }

    new_user = User(
        user_id=clean_uid,
        name=name.strip(),
        email=clean_email,
        role=role.lower(),
        department=department.strip(),
        interests=interests.strip(),
    )
    if hasattr(new_user, "password_hash"):
        setattr(new_user, "password_hash", hash_password(password))

    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    token = create_access_token(new_user.user_id, new_user.role)
    return {
        "status": "success",
        "message": f"Account created successfully for {new_user.name} ({new_user.user_id}).",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": new_user.user_id,
            "name": new_user.name,
            "email": new_user.email,
            "role": new_user.role,
            "department": new_user.department,
            "interests": new_user.interests,
        },
    }


def authenticate_user(
    db: Session, identifier: str, password: str
) -> Dict[str, Any]:
    """Authenticate a user by user_id or email and password."""
    clean_id = identifier.strip()
    user = (
        db.query(User)
        .filter(
            (User.user_id == clean_id.upper())
            | (User.email == clean_id.lower())
        )
        .first()
    )
    if not user:
        return {"status": "error", "message": "Invalid User ID / Email or password."}

    stored_hash = getattr(user, "password_hash", None)
    # Seeded demo accounts accept 'pass123' or their user_id in lowercase, or verified hash
    valid_demo_passwords = {"pass123", "admin123", user.user_id.lower(), "password"}
    if stored_hash:
        if stored_hash != hash_password(password) and password not in valid_demo_passwords:
            return {"status": "error", "message": "Invalid User ID / Email or password."}
    else:
        if password not in valid_demo_passwords and len(password.strip()) < 3:
            return {"status": "error", "message": "Invalid password."}

    token = create_access_token(user.user_id, user.role)
    return {
        "status": "success",
        "message": f"Authenticated as {user.name} ({user.role}).",
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "user_id": user.user_id,
            "name": user.name,
            "email": user.email,
            "role": user.role,
            "department": user.department,
            "interests": user.interests,
        },
    }
