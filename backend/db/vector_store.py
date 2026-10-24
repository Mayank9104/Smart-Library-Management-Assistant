import hashlib
from typing import List, Optional
import chromadb
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models import Resource


class DeterministicHashEmbeddingFunction(chromadb.EmbeddingFunction):
    """
    Lightweight, offline-safe fallback embedding function if HuggingFace model
    weights have not been downloaded yet or when running fast unit tests.
    """

    def __call__(self, input: chromadb.Documents) -> chromadb.Embeddings:
        embeddings = []
        for text in input:
            vec = [0.0] * 64
            tokens = [t.strip(".,:;!?()[]\"'").lower() for t in text.split()]
            for token in tokens:
                if not token:
                    continue
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                idx = h % 64
                vec[idx] += 1.0
            norm = sum(x * x for x in vec) ** 0.5 or 1.0
            embeddings.append([x / norm for x in vec])
        return embeddings


_chroma_client: Optional[chromadb.ClientAPI] = None
_embedding_fn = None


def get_embedding_function():
    """Load sentence-transformers locally if available, else deterministic fallback."""
    global _embedding_fn
    if _embedding_fn is not None:
        return _embedding_fn

    if settings.environment == "test":
        _embedding_fn = DeterministicHashEmbeddingFunction()
        return _embedding_fn

    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        _embedding_fn = SentenceTransformerEmbeddingFunction(
            model_name=settings.embedding_model_name
        )
    except Exception:
        _embedding_fn = DeterministicHashEmbeddingFunction()
    return _embedding_fn


def get_chroma_collection():
    """Return or create the persistent ChromaDB collection for library resources."""
    global _chroma_client
    if _chroma_client is None:
        if settings.environment == "test":
            _chroma_client = chromadb.EphemeralClient()
        else:
            _chroma_client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

    return _chroma_client.get_or_create_collection(
        name="library_catalog",
        embedding_function=get_embedding_function(),
        metadata={"hnsw:space": "cosine"},
    )


def _resource_to_document(res: Resource) -> str:
    return (
        f"Title: {res.title}\n"
        f"Authors: {res.authors}\n"
        f"Type: {res.resource_type}\n"
        f"Subject: {res.subject}\n"
        f"Difficulty: {res.difficulty_level}\n"
        f"Description: {res.description}"
    )


def sync_catalog_to_vector_store(db: Session) -> dict:
    """Index all SQLite catalog resources into ChromaDB (idempotent upsert)."""
    collection = get_chroma_collection()
    resources: List[Resource] = db.query(Resource).all()
    if not resources:
        return {"status": "empty", "indexed_count": 0}

    ids = [r.resource_code for r in resources]
    documents = [_resource_to_document(r) for r in resources]
    metadatas = [
        {
            "resource_code": r.resource_code,
            "title": r.title,
            "authors": r.authors,
            "resource_type": r.resource_type,
            "subject": r.subject,
            "difficulty_level": r.difficulty_level,
            "branch": r.branch,
            "shelf_location": r.shelf_location,
        }
        for r in resources
    ]
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return {"status": "synced", "indexed_count": len(ids)}


def index_single_resource(res: Resource) -> None:
    """Immediately index a newly created or updated resource without code changes."""
    collection = get_chroma_collection()
    collection.upsert(
        ids=[res.resource_code],
        documents=[_resource_to_document(res)],
        metadatas=[
            {
                "resource_code": res.resource_code,
                "title": res.title,
                "authors": res.authors,
                "resource_type": res.resource_type,
                "subject": res.subject,
                "difficulty_level": res.difficulty_level,
                "branch": res.branch,
                "shelf_location": res.shelf_location,
            }
        ],
    )


def semantic_catalog_search(
    db: Session,
    query: str,
    top_k: int = 4,
    difficulty_level: Optional[str] = None,
    resource_type: Optional[str] = None,
) -> dict:
    """
    Hybrid Semantic + Grounded Catalog Search:
    1. Queries ChromaDB vector embeddings for semantic relevance.
    2. Hydrates live availability/holdings directly from authoritative SQLite DB.
    3. Enforces lexical/semantic grounding so fabricated queries return `not_found`.
    """
    if not query or not query.strip():
        return {"status": "not_found", "message": "Empty search query.", "results": []}

    collection = get_chroma_collection()
    if collection.count() == 0:
        sync_catalog_to_vector_store(db)

    where_filter = {}
    if difficulty_level and difficulty_level.strip():
        where_filter["difficulty_level"] = difficulty_level.strip().lower()
    if resource_type and resource_type.strip():
        where_filter["resource_type"] = resource_type.strip().lower()

    query_kwargs = {
        "query_texts": [query.strip()],
        "n_results": min(top_k, max(collection.count(), 1)),
    }
    if len(where_filter) == 1:
        query_kwargs["where"] = where_filter
    elif len(where_filter) > 1:
        query_kwargs["where"] = {"$and": [{k: v} for k, v in where_filter.items()]}

    raw = collection.query(**query_kwargs)
    ids = raw.get("ids", [[]])[0]
    distances = raw.get("distances", [[]])[0]

    # Stopwords to ignore when checking grounding overlap
    stopwords = {
        "find", "book", "books", "paper", "papers", "on", "about", "for",
        "the", "a", "an", "in", "of", "to", "and", "with", "related",
        "beginner", "friendly", "intermediate", "advanced", "resources", "resource",
    }
    query_terms = {
        w.strip(".,:;!?()[]\"'").lower()
        for w in query.split()
        if len(w.strip(".,:;!?()[]\"'")) > 2
    } - stopwords

    grounded_results = []
    for code, dist in zip(ids, distances):
        # Cosine distance threshold: reject completely unrelated matches
        if dist is not None and dist > 0.78:
            continue

        res = db.query(Resource).filter(Resource.resource_code == code).first()
        if not res:
            continue

        haystack = f"{res.title} {res.subject} {res.description} {res.authors} {res.resource_code}".lower()
        has_term_overlap = any(term in haystack for term in query_terms) if query_terms else True

        # Require either strong vector similarity (< 0.55) or lexical domain overlap
        if not has_term_overlap and (dist is None or dist > 0.55):
            continue

        grounded_results.append(
            {
                "resource_code": res.resource_code,
                "title": res.title,
                "authors": res.authors,
                "resource_type": res.resource_type,
                "subject": res.subject,
                "difficulty_level": res.difficulty_level,
                "description": res.description,
                "branch": res.branch,
                "shelf_location": res.shelf_location,
                "available_copies": res.available_copies,
                "total_copies": res.total_copies,
                "digital_url": res.digital_url,
                "relevance_score": round(max(0.0, 1.0 - float(dist or 0.0)), 3),
            }
        )

    if not grounded_results:
        return {
            "status": "not_found",
            "message": f"not_found: No authorized library resources found matching '{query}'.",
            "results": [],
        }

    return {
        "status": "success",
        "count": len(grounded_results),
        "results": grounded_results,
    }
