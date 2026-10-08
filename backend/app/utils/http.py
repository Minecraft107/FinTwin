"""Consistent JSON envelope for every response.

Success: {"data": ..., "meta": {...}}
Error:   {"error": {"code": "...", "message": "...", "details": {...}}}
"""

import logging
from typing import Any

from flask import Flask, jsonify
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from werkzeug.exceptions import HTTPException

from app.extensions import db

logger = logging.getLogger(__name__)


def ok(data: Any = None, meta: dict | None = None, status: int = 200):
    return jsonify({"data": data, "meta": meta or {}}), status


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.details = details


def error_response(status: int, code: str, message: str, details: Any = None):
    return jsonify({"error": {"code": code, "message": message, "details": details or {}}}), status


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(ApiError)
    def _api_error(e: ApiError):
        db.session.rollback()
        return error_response(e.status, e.code, e.message, e.details)

    @app.errorhandler(ValidationError)
    def _validation_error(e: ValidationError):
        db.session.rollback()
        details = e.errors(include_url=False, include_context=False, include_input=False)
        return error_response(400, "VALIDATION_ERROR", "Request validation failed.", details)

    @app.errorhandler(IntegrityError)
    def _integrity_error(e: IntegrityError):
        db.session.rollback()
        logger.warning("Integrity error: %s", e.orig)
        return error_response(409, "CONFLICT", "The request conflicts with existing data.")

    @app.errorhandler(OperationalError)
    def _db_unavailable(e: OperationalError):
        db.session.rollback()
        logger.error("Database unavailable: %s", e.orig)
        return error_response(503, "DB_UNAVAILABLE", "The database is temporarily unavailable.")

    @app.errorhandler(HTTPException)
    def _http_error(e: HTTPException):
        db.session.rollback()
        code = (e.name or "HTTP_ERROR").upper().replace(" ", "_")
        return error_response(e.code or 500, code, e.description or e.name)

    @app.errorhandler(Exception)
    def _unhandled(e: Exception):
        db.session.rollback()
        logger.exception("Unhandled error")
        return error_response(500, "INTERNAL_ERROR", "An unexpected error occurred.")
