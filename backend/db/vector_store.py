import hashlib
import re
from typing import Any, Dict, List, Optional
import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from sqlalchemy.orm import Session
from backend.config import settings
from backend.models import Resource


class DeterministicHashEmbeddingFunction(EmbeddingFunction):
    """Deterministic local embedding function for fast, offline-safe semantic indexing."""

    def __init__(self) -> None:
        pass

    @staticmethod
    def name() -> str:
        return "deterministic_hash_embedding"

    def get_config(self) -> Dict[str, Any]:
        return {"name": self.name()}

    @staticmethod
    def build_from_config(config: Dict[str, Any]) -> "DeterministicHashEmbeddingFunction":
        return DeterministicHashEmbeddingFunction()

    def __call__(self, input: Documents) -> Embeddings:
        embeddings: Embeddings = []
        dim = 64
        for text in input:
            vec = [0.0] * dim
            tokens = re.findall(r"\w+", text.lower())
            for token in tokens:
                h = int(hashlib.md5(token.encode("utf-8")).hexdigest(), 16)
                idx = h % dim
                sign = 1.0 if ((h >> 8) & 1) == 0 else -1.0
                vec[idx] += sign
            norm = sum(x * x for x in vec) ** 0.5
            if norm > 0:
                vec = [x / norm for x in vec]
            embeddings.append(vec)
        return embeddings


_chroma_client = None
_embedding_fn = DeterministicHashEmbeddingFunction()


def get_chroma_collection():
    """Return or create the ChromaDB collection for catalog resources."""
    global _chroma_client
    if _chroma_client is None:
        if getattr(settings, "environment", "development") == "test":
            _chroma_client = chromadb.EphemeralClient()
        else:
            persist_dir = getattr(settings, "chroma_persist_dir", "./data/chroma")
            _chroma_client = chromadb.PersistentClient(path=persist_dir)
    return _chroma_client.get_or_create_collection(
        name="library_catalog",
        embedding_function=_embedding_fn,
    )


def _get_resource_text_fields(resource: Resource) -> tuple[str, str]:
    """Safely extract tags/keywords and description/summary from a Resource model."""
    tags = (
        getattr(resource, "tags", None)
        or getattr(resource, "keywords", None)
        or getattr(resource, "course_code", None)
        or ""
    )
    desc = (
        getattr(resource, "description", None)
        or getattr(resource, "summary", None)
        or getattr(resource, "abstract", None)
        or ""
    )
    return str(tags), str(desc)


def index_single_resource(resource: Resource) -> None:
    """Index or update a single Resource in ChromaDB dynamically (supports live updates)."""
    collection = get_chroma_collection()
    tags, desc = _get_resource_text_fields(resource)
    doc_text = (
        f"Title: {resource.title}. Authors: {resource.authors}. "
        f"Subject: {resource.subject}. Type: {resource.resource_type}. "
        f"Difficulty: {resource.difficulty_level}. "
        f"Tags: {tags}. Description: {desc}"
    )
    metadata = {
        "resource_code": resource.resource_code,
        "title": resource.title,
        "subject": resource.subject,
        "resource_type": resource.resource_type,
        "difficulty_level": resource.difficulty_level,
    }
    collection.upsert(
        ids=[resource.resource_code],
        documents=[doc_text],
        metadatas=[metadata],
    )


# Alias for backward compatibility
index_resource_in_vector_store = index_single_resource


def sync_catalog_to_vector_store(db: Session) -> int:
    """Synchronize all SQLite catalog resources into ChromaDB."""
    resources = db.query(Resource).all()
    for res in resources:
        index_single_resource(res)
    return len(resources)


def semantic_catalog_search(
    db: Session,
    query: str,
    difficulty_level: Optional[str] = None,
    resource_type: Optional[str] = None,
    top_k: int = 5,
) -> Dict[str, Any]:
    """Perform hybrid semantic + metadata search grounded strictly in SQLite catalog holdings."""
    sync_catalog_to_vector_store(db)
    collection = get_chroma_collection()

    total_docs = collection.count()
    if total_docs == 0:
        return {"status": "not_found", "count": 0, "results": []}

    q_lower = query.lower()
    stop_words = {
        "find", "books", "book", "on", "for", "the", "a", "an", "in", "of",
        "to", "and", "or", "is", "are", "available", "papers", "related",
        "about", "recommend", "suggest", "beginner", "intermediate", "advanced",
        "resources", "learning", "that", "currently", "title", "not", "present",
        "any", "authorized", "source",
    }
    keywords = [w for w in re.findall(r"\w+", q_lower) if w not in stop_words and len(w) > 2]

    all_resources = db.query(Resource).all()
    lexical_matches = []
    for r in all_resources:
        if difficulty_level and r.difficulty_level.lower() != difficulty_level.lower():
            continue
        if resource_type and r.resource_type.lower() != resource_type.lower():
            continue
        tags, desc = _get_resource_text_fields(r)
        haystack = f"{r.title} {r.authors} {r.subject} {tags} {desc}".lower()
        score = sum(1 for kw in keywords if kw in haystack)
        if score > 0:
            lexical_matches.append((score, r))

    if not lexical_matches:
        return {
            "status": "not_found",
            "message": "No matching resources found in any authorized library source.",
            "count": 0,
            "results": [],
        }

    n_results = min(top_k, total_docs)
    chroma_res = collection.query(query_texts=[query], n_results=n_results)
    vector_rank = {
        code: idx for idx, code in enumerate(chroma_res.get("ids", [[]])[0])
    }

    lexical_matches.sort(
        key=lambda item: (-item[0], vector_rank.get(item[1].resource_code, 999))
    )

    results = []
    for score, r in lexical_matches[:top_k]:
        _, desc = _get_resource_text_fields(r)
        results.append({
            "resource_code": r.resource_code,
            "title": r.title,
            "authors": r.authors,
            "resource_type": r.resource_type,
            "subject": r.subject,
            "difficulty_level": r.difficulty_level,
            "branch": r.branch,
            "shelf_location": r.shelf_location,
            "total_copies": r.total_copies,
            "available_copies": r.available_copies,
            "digital_url": getattr(r, "digital_url", None),
            "description": desc,
            "relevance_score": score,
        })

    return {
        "status": "success",
        "count": len(results),
        "results": results,
    }
