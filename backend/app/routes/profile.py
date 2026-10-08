from flask import Blueprint

from app.extensions import db
from app.models import FinancialProfile
from app.schemas.common import dump, parse_body
from app.schemas.profile import ProfileOut, ProfileUpdate
from app.services.digital_twin.service import recalculate_after_writes
from app.utils.auth import current_user_id, protect
from app.utils.http import ok

bp = recalculate_after_writes(
    protect(Blueprint("profile", __name__, url_prefix="/financial-profile"))
)


def _profile(user_id: int) -> FinancialProfile:
    profile = db.session.scalar(
        db.select(FinancialProfile).where(FinancialProfile.user_id == user_id)
    )
    if profile is None:  # e.g. users created before profiles existed
        profile = FinancialProfile(user_id=user_id)
        db.session.add(profile)
        db.session.flush()
    return profile


@bp.get("")
def get_profile():
    profile = _profile(current_user_id())
    db.session.commit()
    return ok(dump(ProfileOut, profile))


@bp.put("")
def update_profile():
    body = parse_body(ProfileUpdate)
    profile = _profile(current_user_id())
    for name, value in body.model_dump(exclude_unset=True).items():
        if value is not None:
            setattr(profile, name, value)
    db.session.commit()
    return ok(dump(ProfileOut, profile))
