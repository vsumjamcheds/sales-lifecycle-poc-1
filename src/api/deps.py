from __future__ import annotations

from fastapi import Depends, Header
from sqlalchemy.orm import Session

from src.auth.context import RepContext, require_rep_context
from src.database.session import get_db


def get_rep_ctx(
    db: Session = Depends(get_db),
    x_rep_code: str | None = Header(default=None, alias="X-Rep-Code"),
) -> RepContext:
    return require_rep_context(db, x_rep_code)
