from typing import TypeVar

from app.extensions import db
from app.utils.http import ApiError

T = TypeVar("T")


def get_owned(model: type[T], obj_id: int, user_id: int) -> T:
    """Fetch a user-owned row. Rows owned by someone else are reported as 404, not 403,
    so the API never reveals that another user's id exists."""
    obj = db.session.scalar(db.select(model).where(model.id == obj_id, model.user_id == user_id))
    if obj is None:
        raise ApiError(404, "NOT_FOUND", f"{model.__name__} {obj_id} not found.")
    return obj
