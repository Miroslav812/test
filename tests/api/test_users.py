from collections.abc import Callable
from typing import Any
from uuid import uuid4

import allure
import pytest

from restkit.apis.users import UsersApi
from restkit.contracts import Error, User, UserPage, assert_contract, assert_status
from tests.factories import user_payload

pytestmark = [allure.epic("REST API"), allure.feature("Users")]


@pytest.mark.smoke
@pytest.mark.contract
def test_list_users_contract(users: UsersApi) -> None:
    response = users.list(limit=5)
    assert_status(response, 200)
    page = assert_contract(response, UserPage)
    assert page.limit == 5
    assert page.offset == 0
    assert len(page.items) <= 5
    assert page.total >= len(page.items)


@pytest.mark.smoke
@pytest.mark.contract
@pytest.mark.mutation
def test_user_crud(users: UsersApi, create_user: Callable[..., User]) -> None:
    with allure.step("Create a unique user"):
        created = create_user()
    with allure.step("Read persisted data"):
        response = users.get(str(created.id))
        assert_status(response, 200)
        assert assert_contract(response, User) == created
    with allure.step("Update the name and verify persistence"):
        response = users.update(str(created.id), {"name": "Updated Automation User"})
        assert_status(response, 200)
        updated = assert_contract(response, User)
        assert updated.name == "Updated Automation User"
        assert updated.email == created.email
        assert updated.id == created.id
        assert updated.created_at == created.created_at
        assert assert_contract(users.get(str(created.id)), User) == updated
    with allure.step("Delete and verify the record is unavailable"):
        response = users.delete(str(created.id))
        assert_status(response, 204)
        assert response.content == b""
        response = users.get(str(created.id))
        assert_status(response, 404)
        assert assert_contract(response, Error).detail == "User not found"


@pytest.mark.negative
@pytest.mark.mutation
def test_duplicate_email_rejected(users: UsersApi, create_user: Callable[..., User]) -> None:
    created = create_user()
    response = users.create(user_payload(email=str(created.email)))
    assert_status(response, 409)
    assert assert_contract(response, Error).detail == "Email already exists"
    assert assert_contract(users.get(str(created.id)), User) == created


@pytest.mark.negative
@pytest.mark.mutation
@pytest.mark.parametrize(
    "overrides",
    [
        {"name": ""},
        {"name": "   "},
        {"name": "x" * 101},
        {"name": None},
        {"email": "not-an-email"},
        {"email": None},
        {"role": "superuser"},
        {"unexpected": "field"},
    ],
    ids=[
        "empty-name",
        "blank-name",
        "long-name",
        "null-name",
        "invalid-email",
        "null-email",
        "unknown-role",
        "extra-field",
    ],
)
def test_invalid_create_payload(users: UsersApi, overrides: dict[str, Any]) -> None:
    response = users.create(user_payload(**overrides))
    assert_status(response, 422)
    assert isinstance(response.json()["detail"], list)
    assert response.json()["detail"]


@pytest.mark.negative
@pytest.mark.parametrize("limit,offset", [(0, 0), (101, 0), (5, -1)])
def test_invalid_pagination(users: UsersApi, limit: int, offset: int) -> None:
    response = users.list(limit=limit, offset=offset)
    assert_status(response, 422)
    assert response.json()["detail"]


@pytest.mark.contract
def test_page_past_end_is_empty(users: UsersApi) -> None:
    response = users.list(limit=1, offset=1_000_000)
    assert_status(response, 200)
    page = assert_contract(response, UserPage)
    assert page.items == []
    assert page.offset == 1_000_000


@pytest.mark.negative
def test_missing_user(users: UsersApi) -> None:
    response = users.get(str(uuid4()))
    assert_status(response, 404)
    assert assert_contract(response, Error).detail == "User not found"


@pytest.mark.negative
@pytest.mark.mutation
def test_invalid_patch_does_not_change_user(
    users: UsersApi, create_user: Callable[..., User]
) -> None:
    created = create_user()
    response = users.update(str(created.id), {"name": ""})
    assert_status(response, 422)
    assert assert_contract(users.get(str(created.id)), User) == created


@pytest.mark.negative
@pytest.mark.mutation
def test_delete_is_not_repeatable(users: UsersApi, create_user: Callable[..., User]) -> None:
    created = create_user()
    assert_status(users.delete(str(created.id)), 204)
    response = users.delete(str(created.id))
    assert_status(response, 404)
    assert_contract(response, Error)
