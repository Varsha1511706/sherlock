# src/rag.py
"""RAG with cosine similarity and time-decay weighting."""
import json
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

_model = None
_collection = None


def _init():
    global _model, _collection
    if _collection is not None:
        return
    _model = SentenceTransformer("all-MiniLM-L6-v2")
    client = chromadb.PersistentClient(path="./chroma_db")
    _collection = client.get_or_create_collection(
        "incidents", metadata={"hnsw:space": "cosine"})

    if _collection.count() == 0:
        incidents = json.loads(Path("data/incidents.json").read_text(encoding="utf-8"))
        docs = [
            f"{i['summary']}. Root cause: {i['root_cause']}. "
            f"Services: {', '.join(i['services'])}"
            for i in incidents
        ]
        embs = _model.encode(docs, normalize_embeddings=True).tolist()
        _collection.add(
            ids=[i["id"] for i in incidents],
            documents=docs,
            embeddings=embs,
            metadatas=[{
                "root_cause": i["root_cause"],
                "resolution": i["resolution"],
                "services": ",".join(i["services"]),
                "last_seen": i.get("last_seen", "2026-01-01"),
            } for i in incidents],
        )


def _time_decay(last_seen: str) -> float:
    try:
        dt = datetime.fromisoformat(last_seen).replace(tzinfo=timezone.utc)
        days = (datetime.now(timezone.utc) - dt).days
        return max(0.5, 1.0 - days / 365.0)
    except Exception:
        return 1.0


def retrieve_similar(incident: dict, top_k: int = 3) -> list:
    _init()
    query = (f"Services: {', '.join(incident['affected_services'])}. "
             f"Origin: {incident['probable_origin']}. "
             f"Signals: {incident['signals'][:2]}")
    emb = _model.encode([query], normalize_embeddings=True).tolist()
    res = _collection.query(query_embeddings=emb, n_results=top_k * 2)

    out = []
    for i in range(len(res["ids"][0])):
        cos = 1.0 - res["distances"][0][i]  # cosine distance -> similarity
        cos = max(0.0, min(1.0, cos))
        meta = res["metadatas"][0][i]
        decay = _time_decay(meta.get("last_seen", "2026-01-01"))
        out.append({
            "id": res["ids"][0][i],
            "summary": res["documents"][0][i],
            "root_cause": meta["root_cause"],
            "resolution": meta["resolution"],
            "similarity": round(cos, 3),
            "recency_weight": round(decay, 2),
            "final_score": round(cos * decay, 3),
        })

    out.sort(key=lambda x: -x["final_score"])
    return out[:top_k]
