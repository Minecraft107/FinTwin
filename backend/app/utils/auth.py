from flask import Blueprint, Flask
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request

from app.extensions import jwt
from app.utils.http import error_response


def current_user_id() -> int:
    return int(get_jwt_identity())


def protect(bp: Blueprint) -> Blueprint:
    """Require a valid JWT on every route of the blueprint."""

    @bp.before_request
    def _require_jwt() -> None:
        # Must return None: any value returned from before_request becomes the response.
        verify_jwt_in_request()

    return bp


def register_jwt_handlers(app: Flask) -> None:
    @jwt.unauthorized_loader
    def _missing(reason: str):
        return error_response(401, "UNAUTHORIZED", "Authentication required.", {"reason": reason})

    @jwt.invalid_token_loader
    def _invalid(reason: str):
        return error_response(401, "INVALID_TOKEN", "Invalid token.", {"reason": reason})

    @jwt.expired_token_loader
    def _expired(_header, _payload):
        return error_response(401, "TOKEN_EXPIRED", "Session expired. Please log in again.")
