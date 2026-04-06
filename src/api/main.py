from __future__ import annotations

import json
import os
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from sqlalchemy import Integer, cast, func
from sqlalchemy.orm import Session

from src.agents.capacity import run_capacity
from src.agents.compliance_gatekeeper import evaluate_plan_text
from src.agents.scout import run_scout
from src.agents.scribe import run_scribe
from src.agents.strategist import run_strategist
from src.api.deps import get_rep_ctx
from src.auth.context import RepContext
from src.database.audit_logger import log_event
from src.database.models import AuditLog, HCP
from src.database.session import get_db, init_db

app = FastAPI(title="HCP Engagement POC API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    if not os.environ.get("PYTEST_RUNNING"):
        init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/v1/hcps")
def list_hcps(
    db: Session = Depends(get_db),
    ctx: RepContext = Depends(get_rep_ctx),
) -> list[dict[str, Any]]:
    rows = db.query(HCP).filter(HCP.territory_code == ctx.territory_code).order_by(HCP.display_name).all()
    return [
        {"hcp_id": h.id, "display_name": h.display_name, "specialty": h.specialty, "territory_code": h.territory_code}
        for h in rows
    ]


@app.get("/api/v1/scout")
def scout_report(
    db: Session = Depends(get_db),
    ctx: RepContext = Depends(get_rep_ctx),
) -> dict[str, Any]:
    rows = run_scout(db, ctx)
    return {"rep": ctx.code, "territory": ctx.territory_code, "hcps": rows}


@app.get("/api/v1/capacity")
def capacity_report(
    db: Session = Depends(get_db),
    ctx: RepContext = Depends(get_rep_ctx),
) -> dict[str, Any]:
    scout_rows = run_scout(db, ctx)
    cap_rows = run_capacity(db, ctx, scout_rows)
    return {"rep": ctx.code, "territory": ctx.territory_code, "hcps": cap_rows}


class PlanRequest(BaseModel):
    hcp_id: int = Field(..., ge=1)


@app.post("/api/v1/plan")
def build_plan(
    body: PlanRequest,
    db: Session = Depends(get_db),
    ctx: RepContext = Depends(get_rep_ctx),
) -> dict[str, Any]:
    hcp = db.query(HCP).filter(HCP.id == body.hcp_id, HCP.territory_code == ctx.territory_code).one_or_none()
    if not hcp:
        return {"error": "HCP not in territory"}

    log_event(
        db,
        rep_code=ctx.code,
        event_type="plan_requested",
        payload={"hcp_id": body.hcp_id},
    )

    strat = run_strategist(db, ctx, body.hcp_id)
    plan_text = "\n".join(
        [
            f"1) {strat['plan']['step_1']}",
            f"2) {strat['plan']['step_2']}",
            f"3) {strat['plan']['step_3']}",
        ]
    )
    compliance = evaluate_plan_text(plan_text)
    log_event(
        db,
        rep_code=ctx.code,
        event_type="compliance_gatekeeper",
        payload={
            "hcp_id": body.hcp_id,
            "before": plan_text,
            "after": compliance.get("final_text"),
            "status": compliance.get("status"),
            "similarity": compliance.get("similarity"),
            "citation": compliance.get("citation"),
        },
    )
    return {
        "hcp_id": body.hcp_id,
        "strategist": strat,
        "compliance": compliance,
    }


class ScribeRequest(BaseModel):
    hcp_id: int = Field(..., ge=1)
    note: str = Field(..., min_length=3)


@app.post("/api/v1/scribe")
def scribe_sync(
    body: ScribeRequest,
    db: Session = Depends(get_db),
    ctx: RepContext = Depends(get_rep_ctx),
) -> dict[str, Any]:
    hcp = db.query(HCP).filter(HCP.id == body.hcp_id, HCP.territory_code == ctx.territory_code).one_or_none()
    if not hcp:
        return {"error": "HCP not in territory"}
    out = run_scribe(db, ctx, body.hcp_id, body.note)
    return out


class DecisionRequest(BaseModel):
    decision: str = Field(..., description="accept or reject")
    payload: dict[str, Any] = Field(default_factory=dict)


def _audit_payload(payload_json: str) -> Any:
    if not payload_json:
        return {}
    try:
        return json.loads(payload_json)
    except json.JSONDecodeError:
        return {"_raw": payload_json}


@app.get("/api/v1/audit-logs")
@app.get("/api/v1/audit_logs")  # alias (some clients / proxies mishandle hyphens)
def list_audit_logs(
    db: Session = Depends(get_db),
    ctx: RepContext = Depends(get_rep_ctx),
    limit: int = Query(100, ge=1, le=500),
    hcp_id: int | None = Query(None, ge=1, description="If set, only events whose payload includes this hcp_id"),
) -> list[dict[str, Any]]:
    q = db.query(AuditLog).filter(AuditLog.rep_code == ctx.code)
    if hcp_id is not None:
        # ORM-level json_extract (avoids fragile text() bindparam merging with legacy Query)
        q = q.filter(cast(func.json_extract(AuditLog.payload_json, "$.hcp_id"), Integer) == hcp_id)
    rows = q.order_by(AuditLog.id.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "created_at": r.created_at.isoformat() + "Z" if r.created_at else None,
            "rep_code": r.rep_code,
            "event_type": r.event_type,
            "payload": _audit_payload(r.payload_json),
        }
        for r in rows
    ]


@app.post("/api/v1/decision")
def user_decision(
    body: DecisionRequest,
    db: Session = Depends(get_db),
    ctx: RepContext = Depends(get_rep_ctx),
) -> dict[str, str]:
    if body.decision not in {"accept", "reject"}:
        raise HTTPException(status_code=400, detail="decision must be accept or reject")
    log_event(
        db,
        rep_code=ctx.code,
        event_type=f"user_{body.decision}",
        payload=body.payload,
    )
    return {"status": "logged"}
