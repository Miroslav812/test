from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from threading import Barrier
from typing import Any

import httpx

from restkit.apis.users import UsersApi
from restkit.client import ApiClient
from restkit.config import Settings
from restkit.contracts import User, UserPage, assert_contract, assert_status


def read_all_users(users: UsersApi) -> list[User]:
    """Read a stable snapshot; callers must finish their concurrent writers first."""
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
        # Build each connection pool before the barrier; clients are ready before the race starts.
        # The timeout prevents a failed worker from leaving the remaining threads blocked forever.
        with ApiClient(settings) as client:
            barrier.wait()
            return client.request(spec.method, spec.path, json=spec.payload)

    with ThreadPoolExecutor(max_workers=len(specs)) as pool:
        # map preserves input order, allowing PATCH responses to be matched to their writer.
        return list(pool.map(send, specs))
