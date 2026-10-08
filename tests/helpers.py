from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier
from typing import Any
from uuid import UUID

import httpx

from restkit.apis.users import UsersApi
from restkit.client import ApiClient
from restkit.config import Settings
from restkit.contracts import User, UserPage, assert_contract, assert_status


def read_user(users: UsersApi, user_id: str | UUID) -> User:
    """Читаем сохранённую запись с проверкой HTTP-статуса и схемы ответа."""
    response = users.get(str(user_id))
    assert_status(response, 200)
    return assert_contract(response, User)


def delete_test_users(users: UsersApi, user_ids: Iterable[str | UUID]) -> None:
    """Удаляем только записи теста; уже удалённая запись тоже считается очищенной."""
    failures = []
    for user_id in user_ids:
        try:
            response = users.delete(str(user_id))
            if response.status_code not in {204, 404}:
                failures.append(f"HTTP {response.status_code}")
        except httpx.HTTPError as exc:
            failures.append(type(exc).__name__)
    assert not failures, f"Не удалось очистить тестовые данные: {failures}"


def read_all_users(users: UsersApi) -> list[User]:
    """Снимаем полный снимок после завершения всех конкурентных изменений."""
    result: list[User] = []
    while True:
        response = users.list(limit=100, offset=len(result))
        assert_status(response, 200)
        page = assert_contract(response, UserPage)
        assert page.offset == len(result)
        assert len(page.items) <= 100
        result.extend(page.items)
        if len(result) >= page.total:
            assert len(result) == page.total
            assert len({user.id for user in result}) == len(result)
            return result
        assert page.items, "Pagination stopped before the declared total was reached"


@dataclass(frozen=True)
class RequestSpec:
    method: str
    path: str
    payload: dict[str, Any] | None = None


def parallel_requests(settings: Settings, specs: Sequence[RequestSpec]) -> list[httpx.Response]:
    if not 1 <= len(specs) <= 8:
        raise ValueError("Use a small batch of 1-8 requests for concurrency checks")
    barrier = Barrier(len(specs), timeout=10)

    def send(spec: RequestSpec) -> httpx.Response:
        # Клиенты готовы до общего старта. Таймаут барьера исключает зависание при сбое потока.
        with ApiClient(settings) as client:
            barrier.wait()
            return client.request(spec.method, spec.path, json=spec.payload)

    with ThreadPoolExecutor(max_workers=len(specs)) as pool:
        # map сохраняет порядок запросов: каждый PATCH-ответ сопоставляем со своим автором.
        return list(pool.map(send, specs))
