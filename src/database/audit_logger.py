from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from src.database.models import AuditLog


def log_event(db: Session, *, rep_code: str, event_type: str, payload: dict[str, Any]) -> None:
    row = AuditLog(
        rep_code=rep_code,
        event_type=event_type,
        payload_json=json.dumps(payload, default=str),
    )
    db.add(row)
    db.commit()
