from __future__ import annotations

from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.orm import Session

from src.database.models import Rep


@dataclass
class RepContext:
    id: int
    code: str
    territory_code: str


def get_rep_by_code(db: Session, code: str) -> Rep:
    r = db.query(Rep).filter(Rep.code == code).one_or_none()
    if not r:
        raise HTTPException(status_code=401, detail=f"Unknown rep code: {code}")
    return r


def require_rep_context(db: Session, x_rep_code: str | None) -> RepContext:
    if not x_rep_code:
        raise HTTPException(status_code=401, detail="Missing X-Rep-Code header")
    code = x_rep_code.strip()
    rep = get_rep_by_code(db, code)
    return RepContext(id=rep.id, code=rep.code, territory_code=rep.territory_code)
