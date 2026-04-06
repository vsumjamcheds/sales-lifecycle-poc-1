from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy.orm import Session

from src.auth.context import RepContext
from src.constants import ANCHOR_START
from src.database.models import Rep, RepCommitment


def run_capacity(
    db: Session,
    ctx: RepContext,
    scout_rows: list[dict[str, Any]],
    *,
    week_start: date | None = None,
) -> list[dict[str, Any]]:
    rep = db.query(Rep).filter(Rep.id == ctx.id).one()
    ws = week_start or (ANCHOR_START + timedelta(days=7))

    commit = (
        db.query(RepCommitment)
        .filter(RepCommitment.rep_id == rep.id, RepCommitment.week_start == ws)
        .one_or_none()
    )
    committed = commit.committed_visits if commit else 0
    admin_blocks = commit.admin_blocks if commit else 0

    slots = max(0, rep.weekly_visit_cap - committed - admin_blocks)
    friction = rep.travel_friction_score

    out: list[dict[str, Any]] = []
    for i, row in enumerate(scout_rows):
        adjusted = row["priority_score"] * (1 - friction * 0.2) - (i * 0.005)
        in_slot = i < slots
        reason = "within weekly slots" if in_slot else f"deferred (slots remaining {slots})"
        if i >= rep.max_new_targets_per_week:
            reason = "low-priority net-new throttle" if in_slot else reason

        item = {
            **row,
            "capacity_adjusted_score": round(adjusted, 4),
            "capacity_reason": reason,
            "feasible_this_week": in_slot,
        }
        out.append(item)

    feasible = [r for r in out if r["feasible_this_week"]]
    deferred = [r for r in out if not r["feasible_this_week"]]
    feasible.sort(key=lambda x: x["capacity_adjusted_score"], reverse=True)
    deferred.sort(key=lambda x: x["capacity_adjusted_score"], reverse=True)
    merged = feasible + deferred
    for j, row in enumerate(merged, start=1):
        row["capacity_rank"] = j
    return merged
