import socket
import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest
import uvicorn
from pydantic import SecretStr, ValidationError

from demo_api.app import create_app
from restkit.apis.users import UsersApi
from restkit.client import ApiClient
from restkit.config import Settings
from restkit.contracts import User, assert_contract, assert_status
from tests.factories import user_payload
from tests.helpers import read_all_users


def pytest_addoption(parser: pytest.Parser) -> None:
    group = parser.getgroup("REST API")
    group.addoption("--api-mode", choices=["demo", "external"], default="demo")
    group.addoption("--base-url", default=None, help="Override API_BASE_URL in external mode")
    group.addoption(
        "--allow-mutations",
        action="store_true",
        help="Allow tests to create/update/delete data on an external test stand",
    )
    browser = parser.getgroup("Selenium UI")
    browser.addoption("--browser", choices=["chrome", "edge"], default="chrome")
    browser.addoption("--headed", action="store_true", help="Show the browser window")
    browser.addoption("--browser-binary", default=None, help="Custom Chrome/Edge executable")
    browser.addoption("--driver-path", default=None, help="Use an existing compatible WebDriver")
    browser.addoption(
        "--browser-no-sandbox",
        action="store_true",
        help="Disable the browser sandbox only in an already isolated Linux container",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if config.getoption("--api-mode") == "external":
        for item in items:
            if item.get_closest_marker("demo"):
                item.add_marker(pytest.mark.skip(reason="Bundled demo API only"))
            if item.get_closest_marker("mutation") and not config.getoption("--allow-mutations"):
                item.add_marker(
                    pytest.mark.skip(reason="External writes require --allow-mutations")
                )


@pytest.fixture(scope="session")
def demo_url() -> Iterator[str]:
    # Each xdist worker owns an isolated store and OS-assigned port.
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        url = f"http://127.0.0.1:{sock.getsockname()[1]}"
        server = uvicorn.Server(
            uvicorn.Config(
                create_app(), log_level="error", access_log=False, lifespan="off", ws="none"
            )
        )
        thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
        thread.start()
        try:
            deadline = time.monotonic() + 10
            with httpx.Client(base_url=url, timeout=0.5, trust_env=False) as probe:
                while time.monotonic() < deadline and thread.is_alive():
                    try:
                        response = probe.get("/health")
                        if response.status_code == 200 and response.json() == {"status": "ok"}:
                            break
                    except httpx.HTTPError:
                        pass
                    time.sleep(0.05)
                else:
                    pytest.fail("Demo API did not pass its readiness check within 10 seconds")
            yield url
        finally:
            server.should_exit = True
            thread.join(timeout=5)
            if thread.is_alive():
                pytest.fail("Demo API failed to stop")


@pytest.fixture(scope="session")
def settings(request: pytest.FixtureRequest) -> Settings:
    if request.config.getoption("--api-mode") == "demo":
        return Settings(
            base_url=request.getfixturevalue("demo_url"),
            token=None,
            trust_env=False,
            _env_file=None,
        )
    overrides = {}
    if request.config.getoption("--base-url"):
        overrides["base_url"] = request.config.getoption("--base-url")
    try:
        result = Settings(**overrides)
    except ValidationError as exc:
        raise pytest.UsageError("Set a valid API_BASE_URL/--base-url and API_TOKEN") from exc
    if not result.token or not result.token.get_secret_value():
        raise pytest.UsageError("External mode requires API_TOKEN in environment or ignored .env")
    return result


@pytest.fixture(scope="session")
def authorized_settings(request: pytest.FixtureRequest, settings: Settings) -> Settings:
    if request.config.getoption("--api-mode") == "external":
        return settings
    with ApiClient(settings) as client:
        response = client.request(
            "POST", "auth/token", json={"username": "demo", "password": "demo"}
        )
        assert_status(response, 200)
        assert response.json()["token_type"] == "bearer"
        token = SecretStr(response.json()["access_token"])
    return settings.model_copy(update={"token": token})


@pytest.fixture
def api(authorized_settings: Settings) -> Iterator[ApiClient]:
    with ApiClient(authorized_settings) as client:
        yield client


@pytest.fixture
def users(api: ApiClient) -> UsersApi:
    return UsersApi(api)


@pytest.fixture
def create_user(users: UsersApi) -> Iterator[Callable[..., User]]:
    created: list[str] = []

    def create(**overrides: Any) -> User:
        response = users.create(user_payload(**overrides))
        assert_status(response, 201)
        # Register cleanup before schema validation, so contract failures do not leak records.
        created.append(str(response.json()["id"]))
        return assert_contract(response, User)

    yield create
    failures = []
    for user_id in reversed(created):
        try:
            response = users.delete(user_id)
            if response.status_code not in {204, 404}:
                failures.append(f"HTTP {response.status_code}")
        except httpx.HTTPError as exc:
            failures.append(type(exc).__name__)
    assert not failures, f"Test data cleanup failed: {failures}"


@pytest.fixture
def owned_payloads(users: UsersApi) -> Iterator[Callable[..., dict[str, Any]]]:
    emails: set[str] = set()

    def create(**overrides: Any) -> dict[str, Any]:
        payload = user_payload(**overrides)
        # Ownership is recorded before a request, even if a racing response is never validated.
        emails.add(str(payload["email"]))
        return payload

    yield create
    failures = []
    for user in read_all_users(users):
        if str(user.email) not in emails:
            continue
        try:
            response = users.delete(str(user.id))
            if response.status_code not in {204, 404}:
                failures.append(f"HTTP {response.status_code}")
        except httpx.HTTPError as exc:
            failures.append(type(exc).__name__)
    assert not failures, f"Owned test data cleanup failed: {failures}"
