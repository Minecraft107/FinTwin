from flask import Blueprint, current_app
from flask_jwt_extended import create_access_token, jwt_required
from werkzeug.security import check_password_hash, generate_password_hash

from app.extensions import db
from app.models import FinancialProfile, User
from app.schemas.auth import LoginIn, RegisterIn, UserOut
from app.schemas.common import dump, parse_body
from app.utils.auth import current_user_id
from app.utils.http import ApiError, ok

bp = Blueprint("auth", __name__, url_prefix="/auth")

# Compared against when the email is unknown, so response time doesn't reveal which emails exist.
_DUMMY_HASH = generate_password_hash("timing-equalizer")


def _session(user: User) -> dict:
    return {"user": dump(UserOut, user), "access_token": create_access_token(identity=str(user.id))}


@bp.post("/register")
def register():
    body = parse_body(RegisterIn)
    if db.session.scalar(db.select(User.id).where(User.email == body.email)):
        raise ApiError(409, "EMAIL_TAKEN", "An account with this email already exists.")
    user = User(email=body.email, full_name=body.full_name)
    user.set_password(body.password)
    db.session.add(user)
    db.session.flush()
    db.session.add(FinancialProfile(user_id=user.id))
    db.session.commit()
    return ok(_session(user), status=201)


@bp.post("/login")
def login():
    body = parse_body(LoginIn)
    user = db.session.scalar(db.select(User).where(User.email == body.email))
    if user is None:
        check_password_hash(_DUMMY_HASH, body.password)
        raise ApiError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    if not user.check_password(body.password):
        raise ApiError(401, "INVALID_CREDENTIALS", "Incorrect email or password.")
    return ok(_session(user))


@bp.post("/demo")
def demo_login():
    """Log in as the seeded demo user without exposing its password to the browser."""
    if not current_app.config["DEMO_LOGIN_ENABLED"]:
        raise ApiError(404, "NOT_FOUND", "Demo login is disabled.")
    user = db.session.scalar(db.select(User).where(User.email == current_app.config["DEMO_EMAIL"]))
    if user is None:
        raise ApiError(404, "NOT_FOUND", "Demo account not found. Run `flask seed` first.")
    return ok(_session(user))


@bp.get("/me")
@jwt_required()
def me():
    user = db.session.get(User, current_user_id())
    if user is None:
        raise ApiError(401, "UNAUTHORIZED", "Account no longer exists.")
    return ok(dump(UserOut, user))
