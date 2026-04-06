from __future__ import annotations

from datetime import timedelta
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session

from src.auth.context import RepContext
from src.constants import ANCHOR_START
from src.database.models import HCP, InteractionHistory, PrescribingSignal


def _volume_totals(db: Session, hcp_id: int, start: Any, end: Any) -> float:
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


def _interaction_stats(db: Session, hcp_id: int, rep_id: int, start: Any, end: Any) -> tuple[int, int]:
    rows = (
        db.query(InteractionHistory)
        .filter(
            InteractionHistory.hcp_id == hcp_id,
            InteractionHistory.rep_id == rep_id,
            InteractionHistory.interaction_date >= start,
            InteractionHistory.interaction_date <= end,
        )
        .all()
    )
    neg = sum(1 for r in rows if r.sentiment == "negative")
    return len(rows), neg


def run_scout(db: Session, ctx: RepContext) -> list[dict[str, Any]]:
    start_a = ANCHOR_START
    end_a = ANCHOR_START + timedelta(days=6)
    start_b = ANCHOR_START + timedelta(days=7)
    end_b = ANCHOR_START + timedelta(days=13)

    hcps = db.query(HCP).filter(HCP.territory_code == ctx.territory_code).all()
    ranked: list[dict[str, Any]] = []

    for h in hcps:
        va = _volume_totals(db, h.id, start_a, end_a)
        vb = _volume_totals(db, h.id, start_b, end_b)
        ta, na = _interaction_stats(db, h.id, ctx.id, start_a, end_a)
        tb, nb = _interaction_stats(db, h.id, ctx.id, start_b, end_b)

        vol_decline_ratio = (va - vb) / max(va, 1e-6)
        touch_drop = (ta - tb) / max(ta + tb + 1, 1)
        neg_pressure = (nb - na) * 0.15 + nb * 0.1
        score = max(0.0, vol_decline_ratio) * 2.0 + max(0.0, touch_drop) + neg_pressure

        drivers: list[str] = []
        if vb < va * 0.92:
            drivers.append(f"prescribing volume lower in days 8-14 vs 1-7 ({vb:.0f} vs {va:.0f})")
        if tb < ta:
            drivers.append(f"fewer touches in second week ({tb} vs {ta})")
        if nb > na:
            drivers.append("negative sentiment increased in second week")
        if not drivers:
            drivers.append("stable vs baseline window; monitor")

        ranked.append(
            {
                "hcp_id": h.id,
                "display_name": h.display_name,
                "specialty": h.specialty,
                "priority_score": round(score, 4),
                "drivers": drivers,
                "metrics": {
                    "volume_period_a": round(va, 2),
                    "volume_period_b": round(vb, 2),
                    "touches_a": ta,
                    "touches_b": tb,
                    "negative_b": nb,
                },
            }
        )

    ranked.sort(key=lambda x: x["priority_score"], reverse=True)
    for i, row in enumerate(ranked, start=1):
        row["rank"] = i
    return ranked
