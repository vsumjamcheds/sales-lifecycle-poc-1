from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

from src.config import settings

COLLECTION_HCP_MEMORY = "hcp_memory"
COLLECTION_CLAIMS = "claims_master"

_embedding_fn: SentenceTransformerEmbeddingFunction | None = None
_client: chromadb.PersistentClient | None = None


def get_embedding_function() -> SentenceTransformerEmbeddingFunction:
    global _embedding_fn
    if _embedding_fn is None:
        _embedding_fn = SentenceTransformerEmbeddingFunction(model_name="all-MiniLM-L6-v2")
    return _embedding_fn


def get_chroma_client() -> chromadb.PersistentClient:
    global _client
    if _client is None:
        path = Path(settings.chroma_path)
        if not path.is_absolute():
            path = settings.project_root / path
        path.mkdir(parents=True, exist_ok=True)
        _client = chromadb.PersistentClient(path=str(path))
    return _client


def get_hcp_memory_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_HCP_MEMORY,
        embedding_function=get_embedding_function(),
        metadata={"description": "HCP unstructured interaction memory"},
    )


def get_claims_collection():
    client = get_chroma_client()
    return client.get_or_create_collection(
        name=COLLECTION_CLAIMS,
        embedding_function=get_embedding_function(),
        metadata={"description": "Approved claims for compliance gatekeeper"},
    )


def add_hcp_memory(
    hcp_id: int,
    text: str,
    *,
    source: str = "scribe",
    extra_metadata: dict[str, Any] | None = None,
) -> str:
    col = get_hcp_memory_collection()
    md: dict[str, Any] = {"hcp_id": str(hcp_id), "source": source}
    if extra_metadata:
        md.update({k: str(v) if isinstance(v, int) else v for k, v in extra_metadata.items()})
    new_id = f"hcp_{hcp_id}_{uuid.uuid4().hex[:12]}"
    col.add(ids=[new_id], documents=[text], metadatas=[md])
    return new_id


def search_hcp_memory(hcp_id: int, query: str, n_results: int = 5) -> list[dict[str, Any]]:
    col = get_hcp_memory_collection()
    res = col.query(
        query_texts=[query],
        n_results=n_results,
        where={"hcp_id": str(hcp_id)},
    )
    out: list[dict[str, Any]] = []
    ids = res.get("ids") or [[]]
    docs = res.get("documents") or [[]]
    dists = res.get("distances") or [[]]
    for i, doc_id in enumerate(ids[0]):
        out.append(
            {
                "id": doc_id,
                "document": docs[0][i] if docs and docs[0] else "",
                "distance": dists[0][i] if dists and dists[0] else None,
            }
        )
    return out


def seed_claims_phrases(phrases: list[tuple[str, str]]) -> None:
    """phrases: list of (claim_id, approved_text)"""
    col = get_claims_collection()
    existing = col.get(include=[])  # ids only
    if existing and existing.get("ids"):
        col.delete(ids=existing["ids"])
    ids = [p[0] for p in phrases]
    docs = [p[1] for p in phrases]
    col.add(ids=ids, documents=docs, metadatas=[{"claim_id": i} for i in ids])


def search_claims(query: str, n_results: int = 3) -> list[dict[str, Any]]:
    col = get_claims_collection()
    res = col.query(query_texts=[query], n_results=n_results)
    out: list[dict[str, Any]] = []
    ids = res.get("ids") or [[]]
    docs = res.get("documents") or [[]]
    dists = res.get("distances") or [[]]
    metas = res.get("metadatas") or [[]]
    for i, doc_id in enumerate(ids[0]):
        out.append(
            {
                "id": doc_id,
                "document": docs[0][i] if docs and docs[0] else "",
                "distance": dists[0][i] if dists and dists[0] else None,
                "metadata": metas[0][i] if metas and metas[0] else {},
            }
        )
    return out
