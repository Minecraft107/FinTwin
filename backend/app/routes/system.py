import logging

from flask import Blueprint, current_app
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.extensions import db
from app.utils.http import ok

logger = logging.getLogger(__name__)
bp = Blueprint("system", __name__)


@bp.get("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        database = "up"
    except SQLAlchemyError as e:
        db.session.rollback()
        logger.warning("Health check: database down (%s)", e.__class__.__name__)
        database = "down"
    healthy = database == "up"
    return ok(
        {
            "status": "ok" if healthy else "degraded",
            "database": database,
            "environment": current_app.config["APP_ENV"],
        },
        status=200 if healthy else 503,
    )
