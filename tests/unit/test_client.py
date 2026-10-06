import logging
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from restkit.client import ApiClient
from restkit.config import Settings


def config(**overrides: Any) -> Settings:
    return Settings(base_url="https://api.example.com/v1", _env_file=None, **overrides)


@pytest.mark.parametrize(
    "path",
    [
        "https://evil.example/users",
        "//evil.example/users",
        "/users",
        "../users",
        "users/../auth",
        "users\\secret",
        "%2e%2e/users",
    ],
)
def test_client_rejects_paths_that_escape_base_url(path: str) -> None:
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        pytest.fail("Unsafe URL must be rejected before sending a request")

    with (
        ApiClient(config(), transport=httpx.MockTransport(unexpected_request)) as client,
        pytest.raises(ValueError),
    ):
        client.request("GET", path)


def test_client_keeps_base_path_and_does_not_follow_redirects() -> None:
    seen: list[httpx.Request] = []

    def redirect(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(302, headers={"Location": "https://evil.example/users"})

    with ApiClient(
        config(token=SecretStr("secret-token")), transport=httpx.MockTransport(redirect)
    ) as client:
        response = client.request("GET", "users")
    assert response.status_code == 302
    assert len(seen) == 1
    assert str(seen[0].url) == "https://api.example.com/v1/users"
    assert seen[0].headers["authorization"] == "Bearer secret-token"


def test_logs_do_not_include_secrets_or_payloads(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="restkit.client")
    with ApiClient(
        config(token=SecretStr("very-private-token")),
        transport=httpx.MockTransport(lambda _: httpx.Response(201)),
    ) as client:
        client.request(
            "POST", "users", params={"key": "private-query"}, json={"password": "private-password"}
        )
    assert "HTTP POST -> 201" in caplog.text
    for secret in ["very-private-token", "private-query", "private-password"]:
        assert secret not in caplog.text


@pytest.mark.parametrize(
    "url",
    [
        "ftp://api.example.com",
        "https://name:password@api.example.com",
        "https://api.example.com?token=secret",
        "https://api.example.com#fragment",
        "http://",
    ],
)
def test_settings_reject_invalid_base_url(url: str) -> None:
    with pytest.raises(ValidationError):
        Settings(base_url=url, _env_file=None)


@pytest.mark.parametrize("timeout", [0, -1, 121])
def test_settings_reject_unbounded_timeouts(timeout: int) -> None:
    with pytest.raises(ValidationError):
        config(timeout_seconds=timeout)
