from typing import TypeVar

from flask import request
from pydantic import BaseModel, ConfigDict

from app.utils.http import ApiError

M = TypeVar("M", bound=BaseModel)


class InModel(BaseModel):
    """Request bodies: reject unknown fields so typos fail loudly."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class OutModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


def parse_body(model: type[M]) -> M:
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise ApiError(400, "INVALID_JSON", "Request body must be a JSON object.")
    return model.model_validate(data)


def dump(model: type[OutModel], obj) -> dict:
    return model.model_validate(obj).model_dump(mode="json")
