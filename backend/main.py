from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.api import router as api_router
from backend.config import settings
from backend.db import get_db, init_db, sync_catalog_to_vector_store
from backend.services import seed_initial_data

app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Backend API for HCLTech AI-Powered Smart Library Management Assistant",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.on_event("startup")
def startup_event() -> None:
    """Initialize database tables and sync vector embeddings on startup."""
    init_db()
    db = next(get_db())
    try:
        seed_initial_data(db)
        sync_catalog_to_vector_store(db)
    finally:
        db.close()


@app.get("/health", tags=["System"])
def health_check() -> dict:
    """Verify backend health and active LLM configuration."""
    active_model = (
        settings.groq_model
        if settings.llm_provider.lower() == "groq"
        else settings.local_llm_model
    )
    return {
        "status": "healthy",
        "service": settings.app_name,
        "llm_provider": settings.llm_provider,
        "active_model": active_model,
        "embedding_model": settings.embedding_model_name,
    }
