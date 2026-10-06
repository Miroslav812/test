from datetime import datetime
from typing import Literal
from uuid import UUID

import httpx
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class User(Contract):
    id: UUID
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: Literal["user", "admin"]
    created_at: datetime


class UserPage(Contract):
    items: list[User]
    total: int = Field(ge=0)
    limit: int = Field(ge=1, le=100)
    offset: int = Field(ge=0)


class Error(Contract):
    detail: str


def assert_status(response: httpx.Response, expected: int) -> None:
    assert response.status_code == expected, (
        f"{response.request.method}: expected HTTP {expected}, got {response.status_code}"
    )


def assert_contract[Model: BaseModel](response: httpx.Response, model: type[Model]) -> Model:
    assert response.headers.get("content-type", "").split(";")[0] == "application/json"
    return model.model_validate_json(response.content)
