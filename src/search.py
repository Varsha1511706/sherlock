# src/search.py
"""
Semantic + keyword search over log events using sentence-transformers.

Builds an in-memory embedding index on first search call.
"""
import numpy as np
import pandas as pd
from sentence_transformers import SentenceTransformer

_model = None
_index_cache = {}


def _get_model():
    global _model
    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")
    return _model


def _build_index(logs_df: pd.DataFrame):
    """Embed unique messages (deduped) once."""
    key = id(logs_df)
    if key in _index_cache:
        return _index_cache[key]

    unique_msgs = logs_df["message"].drop_duplicates().tolist()
    if not unique_msgs:
        _index_cache[key] = (unique_msgs, np.zeros((0, 384)))
        return _index_cache[key]

    emb = _get_model().encode(unique_msgs, show_progress_bar=False,
                              convert_to_numpy=True, normalize_embeddings=True)
    _index_cache[key] = (unique_msgs, emb)
    return _index_cache[key]


def semantic_search(logs_df: pd.DataFrame, query: str, top_k: int = 20) -> pd.DataFrame:
    """
    Return the top_k log rows whose messages are most similar to `query`.
    Falls back to substring match if index unavailable.
    """
    if logs_df is None or logs_df.empty or not query.strip():
        return logs_df.head(0) if logs_df is not None else pd.DataFrame()

    msgs, emb = _build_index(logs_df)
    if len(msgs) == 0:
        return logs_df.head(0)

    qvec = _get_model().encode([query], convert_to_numpy=True,
                               normalize_embeddings=True)[0]
    scores = emb @ qvec  # cosine similarity since normalized

    # Map back to logs: best score per message
    score_map = {msg: float(s) for msg, s in zip(msgs, scores)}
    out = logs_df.copy()
    out["_score"] = out["message"].map(score_map)

    # Also support plain keyword matches (boost)
    kw_mask = out["message"].str.contains(query, case=False, na=False)
    out.loc[kw_mask, "_score"] = out.loc[kw_mask, "_score"].fillna(0) + 0.5

    out = out.sort_values("_score", ascending=False)
    return out.head(top_k).drop(columns=["_score"])


def similar_logs(logs_df: pd.DataFrame, anchor_message: str, top_k: int = 15) -> pd.DataFrame:
    """Find logs semantically similar to a given anchor message."""
    return semantic_search(logs_df, anchor_message, top_k=top_k)


def cluster_messages(logs_df: pd.DataFrame, top_k: int = 8) -> pd.DataFrame:
    """
    Return most common message templates (simple keyword-based clustering proxy).
    """
    if logs_df is None or logs_df.empty:
        return pd.DataFrame()

    # Normalize message: strip numbers, UUIDs
    import re
    def norm(m):
        m = re.sub(r"\d+", "N", m)
        m = re.sub(r"[0-9a-f]{8,}", "ID", m)
        return m[:120]

    tmp = logs_df.copy()
    tmp["template"] = tmp["message"].map(norm)
    counts = tmp.groupby("template").size().reset_index(name="count")
    counts = counts.sort_values("count", ascending=False).head(top_k)
    return counts