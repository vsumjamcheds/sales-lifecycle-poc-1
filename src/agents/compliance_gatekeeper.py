from __future__ import annotations

import re
from typing import Any

import numpy as np

from src.config import settings
from src.database.vector_store import get_embedding_function, search_claims

BLOCK_PATTERNS = [
    r"off[\s-]?label",
    r"unapproved\s+indication",
    r"pediatric\s+use\s+without",
    r"cure\s+for",
    r"guaranteed\s+outcome",
]


def _cosine_sim(a: list[float], b: list[float]) -> float:
    x = np.array(a, dtype=np.float64)
    y = np.array(b, dtype=np.float64)
    denom = float(np.linalg.norm(x) * np.linalg.norm(y))
    if denom == 0:
        return 0.0
    return float(np.dot(x, y) / denom)


def evaluate_plan_text(plan_text: str) -> dict[str, Any]:
    lowered = plan_text.lower()
    for pat in BLOCK_PATTERNS:
        if re.search(pat, lowered):
            return {
                "status": "BLOCK",
                "final_text": "",
                "citation": None,
                "similarity": None,
                "reason": f"Matched policy pattern: {pat}",
            }

    ef = get_embedding_function()
    emb_plan = ef([plan_text])[0]
    hits = search_claims(plan_text, n_results=3)
    if not hits:
        return {
            "status": "REDLINE",
            "final_text": "Use only IFU-indicated messaging. Contact medical affairs for detailed evidence.",
            "citation": None,
            "similarity": 0.0,
            "reason": "No matching approved claim in corpus",
        }

    best = hits[0]
    claim_text = best["document"]
    emb_claim = ef([claim_text])[0]
    sim = _cosine_sim(emb_plan, emb_claim)
    thr = settings.compliance_similarity_threshold

    if sim >= thr:
        return {
            "status": "VERIFIED",
            "final_text": plan_text,
            "citation": {"claim_id": best["id"], "approved_text": claim_text},
            "similarity": round(sim, 4),
            "reason": "Aligned with approved claim language",
        }

    return {
        "status": "REDLINE",
        "final_text": claim_text,
        "citation": {"claim_id": best["id"], "approved_text": claim_text},
        "similarity": round(sim, 4),
        "reason": f"Similarity {sim:.2f} below threshold {thr}; replaced with approved phrasing",
    }
