from typing import Any

import httpx

from restkit.client import ApiClient


class UsersApi:
    def __init__(self, client: ApiClient) -> None:
        self.client = client

    def create(self, payload: dict[str, Any]) -> httpx.Response:
        return self.client.request("POST", "users", json=payload)

    def get(self, user_id: str) -> httpx.Response:
        return self.client.request("GET", f"users/{user_id}")

    def list(self, *, limit: int = 20, offset: int = 0) -> httpx.Response:
        return self.client.request("GET", "users", params={"limit": limit, "offset": offset})

    def update(self, user_id: str, payload: dict[str, Any]) -> httpx.Response:
        return self.client.request("PATCH", f"users/{user_id}", json=payload)

    def delete(self, user_id: str) -> httpx.Response:
        return self.client.request("DELETE", f"users/{user_id}")
