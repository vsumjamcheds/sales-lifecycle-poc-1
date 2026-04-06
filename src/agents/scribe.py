from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from src.auth.context import RepContext
from src.database.audit_logger import log_event
from src.database.models import InteractionHistory
from src.database.vector_store import add_hcp_memory
from src.llm.claude_client import get_client, model_name


_PII_PATTERNS = [
    re.compile(r"\b(?:Mr|Ms|Mrs|Dr)\.?\s+[A-Z][a-z]+\s+[A-Z][a-z]+\b"),
    re.compile(r"\bpatient\s+[A-Z][a-z]+\b", re.I),
    re.compile(r"\b\d{3}-\d{2}-\d{4}\b"),
]


def scrub_pii(text: str) -> str:
    out = text
    for pat in _PII_PATTERNS:
        out = pat.sub("[REDACTED]", out)
    return out


def run_scribe(
    db: Session,
    ctx: RepContext,
    hcp_id: int,
    raw_note: str,
) -> dict[str, Any]:
    cleaned = scrub_pii(raw_note)
    client = get_client()
    prompt = (
        "Summarize this field note for CRM. Return JSON with keys: "
        "summary (string), objections (array of strings), tasks (array of strings).\n\n"
        f"Note:\n{cleaned}"
    )
    msg = client.messages.create(
        model=model_name(),
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in msg.content if b.type == "text")
    parsed = _parse_scribe_json(text)

    mem_blob = json.dumps(
        {
            "summary": parsed["summary"],
            "objections": parsed["objections"],
            "tasks": parsed["tasks"],
        },
        default=str,
    )
    add_hcp_memory(hcp_id, mem_blob, source="scribe")

    inter = InteractionHistory(
        hcp_id=hcp_id,
        rep_id=ctx.id,
        interaction_date=date.today(),
        interaction_type="visit",
        sentiment="neutral",
        objection="; ".join(parsed["objections"]) if parsed["objections"] else None,
        notes=parsed["summary"][:2000],
    )
    db.add(inter)
    db.commit()

    log_event(
        db,
        rep_code=ctx.code,
        event_type="scribe_sync",
        payload={
            "hcp_id": hcp_id,
            "raw_note": raw_note,
            "scrubbed_note": cleaned,
            "parsed": parsed,
        },
    )
    return {"parsed": parsed, "scrubbed_note": cleaned}


def _parse_scribe_json(text: str) -> dict[str, Any]:
    text = text.strip()
    try:
        start = text.index("{")
        end = text.rindex("}") + 1
        obj = json.loads(text[start:end])
        return {
            "summary": str(obj.get("summary", "")),
            "objections": list(obj.get("objections", [])),
            "tasks": list(obj.get("tasks", [])),
        }
    except (ValueError, json.JSONDecodeError):
        return {"summary": text[:500], "objections": [], "tasks": []}
