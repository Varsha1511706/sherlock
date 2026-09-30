# src/llm_client.py
"""LLM client with response caching and cost accounting."""
import hashlib
import json
import os
from pathlib import Path
from datetime import datetime

from cachetools import TTLCache

CACHE = TTLCache(maxsize=256, ttl=3600)
LEDGER = Path("data/llm_ledger.jsonl")


def _hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def call_llm(prompt: str, model: str = "gpt-4o-mini") -> tuple[str, dict]:
    """Returns (response_text, usage). Cached by prompt hash."""
    key = _hash(prompt)
    if key in CACHE:
        return CACHE[key], {"cached": True, "tokens_in": 0, "tokens_out": 0}

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return "", {"error": "no_api_key", "tokens_in": 0, "tokens_out": 0}

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0.2,
        )
        text = resp.choices[0].message.content
        usage = {
            "tokens_in": resp.usage.prompt_tokens,
            "tokens_out": resp.usage.completion_tokens,
            "model": model,
            "ts": datetime.utcnow().isoformat(),
            "cached": False,
        }
        CACHE[key] = text
        with LEDGER.open("a", encoding="utf-8") as f:
            f.write(json.dumps(usage) + "\n")
        return text, usage
    except Exception as e:
        return "", {"error": str(e), "tokens_in": 0, "tokens_out": 0}
