from collections import Counter
from collections.abc import Callable
from datetime import timedelta
from typing import Any
from uuid import uuid4

import allure
import pytest
from pydantic import SecretStr

from restkit.apis.users import UsersApi
from restkit.client import ApiClient
from restkit.config import Settings
from restkit.contracts import Error, User, UserPage, assert_contract, assert_status
from tests.helpers import RequestSpec, parallel_requests, read_all_users

pytestmark = [
    pytest.mark.advanced,
    pytest.mark.demo,
    pytest.mark.mutation,
    allure.epic("REST API"),
    allure.feature("Consistency and concurrent writes"),
]


@pytest.mark.contract
@pytest.mark.parametrize("role", ["user", "admin"])
@pytest.mark.parametrize(
    "name",
    ["A", "x" * 100, "  Мария Ли  ", "李雷🙂"],
    ids=["minimum", "maximum", "trimmed-unicode", "multibyte"],
)
def test_valid_boundaries_preserve_normalized_data(
    users: UsersApi, create_user: Callable[..., User], name: str, role: str
) -> None:
    created = create_user(name=name, role=role)
    assert created.name == name.strip()
    assert created.role == role
    assert created.created_at.utcoffset() == timedelta(0)
    response = users.get(str(created.id))
    assert_status(response, 200)
    assert assert_contract(response, User) == created


@pytest.mark.negative
@pytest.mark.parametrize("field", ["id", "email", "role", "created_at", "unexpected"])
def test_patch_cannot_modify_protected_fields(
    users: UsersApi, create_user: Callable[..., User], field: str
) -> None:
    original = create_user()
    values = {
        "id": str(uuid4()),
        "email": "other@example.com",
        "role": "admin",
        "created_at": "2000-01-01T00:00:00Z",
        "unexpected": True,
    }
    before = read_all_users(users)
    response = users.update(str(original.id), {"name": "Attempted change", field: values[field]})
    assert_status(response, 422)
    # Ошибка одного поля отклоняет весь PATCH, даже если новое имя само по себе допустимо.
    assert read_all_users(users) == before


@pytest.mark.negative
@pytest.mark.parametrize(
    "name", [None, "   ", "x" * 101, 123, []], ids=["null", "blank", "too-long", "number", "array"]
)
def test_invalid_patch_does_not_partially_change_data(
    users: UsersApi, create_user: Callable[..., User], name: Any
) -> None:
    original = create_user()
    before = read_all_users(users)
    assert_status(users.update(str(original.id), {"name": name}), 422)
    assert read_all_users(users) == before


@pytest.mark.negative
@pytest.mark.parametrize(
    "body",
    [b"", b'{"name":', b"null", b"[]", b"{}", b'"scalar"'],
    ids=["empty", "broken-json", "null", "array", "missing-fields", "scalar"],
)
def test_invalid_request_body_has_no_side_effects(
    api: ApiClient, users: UsersApi, create_user: Callable[..., User], body: bytes
) -> None:
    create_user()
    before = read_all_users(users)
    response = api.request(
        "POST", "users", content=body, headers={"Content-Type": "application/json"}
    )
    assert_status(response, 422)
    assert response.json()["detail"]
    assert read_all_users(users) == before


@pytest.mark.contract
@pytest.mark.parametrize("limit", [1, 2, 3, 100])
def test_pagination_remains_complete_after_delete_and_insert(
    users: UsersApi, create_user: Callable[..., User], limit: int
) -> None:
    baseline = read_all_users(users)
    batch = [create_user(name=f"Page item {index}") for index in range(7)]

    def check(expected: list[User]) -> None:
        observed: list[User] = []
        for offset in range(0, len(expected), limit):
            response = users.list(limit=limit, offset=offset)
            assert_status(response, 200)
            page = assert_contract(response, UserPage)
            assert (page.limit, page.offset, page.total) == (limit, offset, len(expected))
            assert len(page.items) == min(limit, len(expected) - offset)
            observed.extend(page.items)
        assert observed == expected
        assert len({user.id for user in observed}) == len(observed)
        response = users.list(limit=limit, offset=len(expected))
        assert_status(response, 200)
        assert assert_contract(response, UserPage).items == []

    with allure.step("Проверить все страницы, порядок, total и отсутствие дубликатов"):
        check(baseline + batch)
    with allure.step("Удалить запись из середины и добавить новую"):
        assert_status(users.delete(str(batch[3].id)), 204)
        appended = create_user(name="Appended after deletion")
        check(baseline + batch[:3] + batch[4:] + [appended])


def test_deleted_email_can_be_reused_without_reusing_id(
    users: UsersApi, create_user: Callable[..., User]
) -> None:
    original = create_user()
    assert_status(users.delete(str(original.id)), 204)
    replacement = create_user(email=str(original.email), name="Replacement", role="admin")
    assert replacement.id != original.id
    assert replacement.email == original.email
    assert_status(users.get(str(original.id)), 404)
    assert assert_contract(users.get(str(replacement.id)), User) == replacement
    assert [user.id for user in read_all_users(users) if user.email == original.email] == [
        replacement.id
    ]


@pytest.mark.negative
def test_patch_deleted_user_does_not_resurrect_record(
    users: UsersApi, create_user: Callable[..., User]
) -> None:
    original = create_user()
    assert_status(users.delete(str(original.id)), 204)
    before = read_all_users(users)
    response = users.update(str(original.id), {"name": "Must not resurrect"})
    assert_status(response, 404)
    assert assert_contract(response, Error).detail == "User not found"
    assert read_all_users(users) == before


@pytest.mark.concurrency
def test_parallel_duplicate_creates_have_exactly_one_winner(
    users: UsersApi,
    authorized_settings: Settings,
    owned_payloads: Callable[..., dict[str, Any]],
) -> None:
    payload = owned_payloads()
    replies = parallel_requests(authorized_settings, [RequestSpec("POST", "users", payload)] * 8)
    assert Counter(reply.status_code for reply in replies) == {201: 1, 409: 7}
    winner = next(reply for reply in replies if reply.status_code == 201)
    saved = assert_contract(winner, User)
    assert saved.email == payload["email"]
    for reply in replies:
        if reply.status_code == 409:
            assert assert_contract(reply, Error).detail == "Email already exists"
    assert [user for user in read_all_users(users) if user.email == saved.email] == [saved]


@pytest.mark.concurrency
def test_parallel_unique_creates_do_not_lose_records(
    users: UsersApi,
    authorized_settings: Settings,
    owned_payloads: Callable[..., dict[str, Any]],
) -> None:
    payloads = [owned_payloads(name=f"Parallel user {index}") for index in range(8)]
    replies = parallel_requests(
        authorized_settings, [RequestSpec("POST", "users", payload) for payload in payloads]
    )
    saved = []
    for payload, reply in zip(payloads, replies, strict=True):
        assert_status(reply, 201)
        user = assert_contract(reply, User)
        assert (user.email, user.name) == (payload["email"], payload["name"])
        saved.append(user)
    assert len({user.id for user in saved}) == 8
    persisted = {user.id: user for user in read_all_users(users)}
    assert all(persisted[user.id] == user for user in saved)


@pytest.mark.concurrency
def test_parallel_deletes_have_one_success(
    users: UsersApi, authorized_settings: Settings, create_user: Callable[..., User]
) -> None:
    original = create_user()
    replies = parallel_requests(
        authorized_settings, [RequestSpec("DELETE", f"users/{original.id}")] * 8
    )
    assert Counter(reply.status_code for reply in replies) == {204: 1, 404: 7}
    for reply in replies:
        if reply.status_code == 204:
            assert reply.content == b""
        else:
            assert assert_contract(reply, Error).detail == "User not found"
    assert_status(users.get(str(original.id)), 404)
    assert original.id not in {user.id for user in read_all_users(users)}


@pytest.mark.concurrency
def test_parallel_updates_acknowledge_each_writer_without_corrupting_identity(
    users: UsersApi, authorized_settings: Settings, create_user: Callable[..., User]
) -> None:
    original = create_user()
    names = [f"Writer {index}" for index in range(8)]
    replies = parallel_requests(
        authorized_settings,
        [RequestSpec("PATCH", f"users/{original.id}", {"name": name}) for name in names],
    )
    for name, reply in zip(names, replies, strict=True):
        assert_status(reply, 200)
        assert assert_contract(reply, User) == original.model_copy(update={"name": name})
    response = users.get(str(original.id))
    assert_status(response, 200)
    final = assert_contract(response, User)
    # Порядок завершения не задан: контракт не содержит версии для оптимистической блокировки.
    assert final.name in names
    assert final == original.model_copy(update={"name": final.name})


@pytest.mark.negative
@pytest.mark.parametrize("method", ["POST", "GET", "PATCH", "DELETE"])
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_unauthorized_operations_leave_store_unchanged(
    users: UsersApi,
    create_user: Callable[..., User],
    authorized_settings: Settings,
    owned_payloads: Callable[..., dict[str, Any]],
    method: str,
    token: str | None,
) -> None:
    original = create_user()
    candidate = owned_payloads()
    before = read_all_users(users)
    config = authorized_settings.model_copy(update={"token": SecretStr(token) if token else None})
    path = "users" if method == "POST" else f"users/{original.id}"
    payload = candidate if method == "POST" else {"name": "Unauthorized change"}
    with ApiClient(config) as client:
        reply = client.request(method, path, json=payload if method in {"POST", "PATCH"} else None)
    assert_status(reply, 401)
    assert reply.headers["www-authenticate"] == "Bearer"
    assert assert_contract(reply, Error).detail == "Unauthorized"
    assert read_all_users(users) == before


@pytest.mark.negative
def test_unsupported_method_has_no_side_effects(
    api: ApiClient, users: UsersApi, create_user: Callable[..., User]
) -> None:
    original = create_user()
    before = read_all_users(users)
    reply = api.request("PUT", f"users/{original.id}", json={"name": "Unsupported"})
    assert_status(reply, 405)
    assert "PUT" not in reply.headers["allow"]
    assert read_all_users(users) == before
