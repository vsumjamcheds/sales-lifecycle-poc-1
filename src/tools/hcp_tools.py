"""
Tool functions for Claude (docstrings used in tool definitions).
All queries MUST be scoped by territory via RepContext.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.auth.context import RepContext
from src.database.models import HCP, InteractionHistory, PrescribingSignal
from src.database.vector_store import search_hcp_memory


def fetch_hcp_performance(db: Session, ctx: RepContext, hcp_id: int) -> dict[str, Any]:
    """
    Return prescribing totals for period A (days 1-7) vs B (days 8-14) and recent interactions
    for one HCP in the rep's territory.
    """
    hcp = (
        db.query(HCP)
        .filter(HCP.id == hcp_id, HCP.territory_code == ctx.territory_code)
        .one_or_none()
    )
    if not hcp:
        return {"error": "HCP not found in territory", "hcp_id": hcp_id}

    from datetime import timedelta

    from src.constants import ANCHOR_START

    start_a = ANCHOR_START
    end_a = ANCHOR_START + timedelta(days=6)
    start_b = ANCHOR_START + timedelta(days=7)
    end_b = ANCHOR_START + timedelta(days=13)

    def vol_sum(start, end):
        q = (
            db.query(func.coalesce(func.sum(PrescribingSignal.volume), 0.0))
            .filter(
                PrescribingSignal.hcp_id == hcp_id,
                PrescribingSignal.signal_date >= start,
                PrescribingSignal.signal_date <= end,
            )
            .scalar()
        )
        return float(q or 0)

    interactions = (
        db.query(InteractionHistory)
        .filter(
            InteractionHistory.hcp_id == hcp_id,
            InteractionHistory.rep_id == ctx.id,
        )
        .order_by(InteractionHistory.interaction_date.desc())
        .limit(8)
        .all()
    )

    return {
        "hcp_id": hcp_id,
        "display_name": hcp.display_name,
        "specialty": hcp.specialty,
        "volume_period_a": vol_sum(start_a, end_a),
        "volume_period_b": vol_sum(start_b, end_b),
        "interactions": [
            {
                "date": str(x.interaction_date),
                "type": x.interaction_type,
                "sentiment": x.sentiment,
                "objection": x.objection,
            }
            for x in interactions
        ],
    }


def search_hcp_memory_tool(hcp_id: int, query: str) -> list[dict[str, Any]]:
    """
    Semantic search over unstructured HCP interaction memory (vector store).
    """
    return search_hcp_memory(hcp_id, query, n_results=5)
