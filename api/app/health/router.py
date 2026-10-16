from typing import Annotated

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.db import get_db

router = APIRouter(tags=["health"])


class Health(BaseModel):
    status: str
    database: str


@router.get("/api/health")
def health(response: Response, db: Annotated[Session, Depends(get_db)]) -> Health:
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = 503
        return Health(status="degraded", database="unreachable")
    return Health(status="ok", database="ok")
