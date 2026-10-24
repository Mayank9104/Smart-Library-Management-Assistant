from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from backend.db import get_db, sync_catalog_to_vector_store
from backend.models import User
from backend.schemas import ChatRequest, ChatResponse
from backend.services import (
    get_librarian_analytics_report,
    seed_initial_data,
)
from backend.db.vector_store import semantic_catalog_search
from backend.ai import process_Library_assistant_query

router = APIRouter(prefix="/api/v1", tags=["Library API"])


@router.post("/seed", summary="Seed initial library data")
def seed_database(db: Session = Depends(get_db)) -> dict:
    """Populate database with sample users, catalog resources, and loans."""
    result = seed_initial_data(db)
    sync_catalog_to_vector_store(db)
    return result


@router.post("/chat", response_model=ChatResponse, summary="Process AI Assistant Chat Query")
def chat_with_assistant(payload: ChatRequest, db: Session = Depends(get_db)) -> ChatResponse:
    """Send a natural-language query to the AI Smart Library Assistant."""
    if db.query(User).count() == 0:
        seed_initial_data(db)
        sync_catalog_to_vector_store(db)

    response = process_Library_assistant_query(
        db=db, user_id=payload.user_id, message=payload.message
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
    if db.query(User).count() == 0:
        seed_initial_data(db)
        sync_catalog_to_vector_store(db)

    return semantic_catalog_search(
        db=db, query=q, difficulty_level=difficulty, resource_type=resource_type
    )


@router.get("/analytics", summary="Librarian Circulation & Demand Analytics")
def get_analytics(db: Session = Depends(get_db)) -> dict:
    """Retrieve Pandas-powered analytics for librarian operations."""
    if db.query(User).count() == 0:
        seed_initial_data(db)
        sync_catalog_to_vector_store(db)

    return get_librarian_analytics_report(db=db)
