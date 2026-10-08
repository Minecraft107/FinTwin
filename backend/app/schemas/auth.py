from datetime import datetime

from pydantic import EmailStr, Field, field_validator

from app.schemas.common import InModel, OutModel


class RegisterIn(InModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()

    @field_validator("password")
    @classmethod
    def _strength(cls, v: str) -> str:
        if not (any(c.isalpha() for c in v) and any(c.isdigit() for c in v)):
            raise ValueError("must contain at least one letter and one digit")
        return v


class LoginIn(InModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    @field_validator("email")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.lower()


class UserOut(OutModel):
    id: int
    email: str
    full_name: str
    created_at: datetime
