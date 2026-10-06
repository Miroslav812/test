import allure
import pytest
from pydantic import SecretStr

from restkit.client import ApiClient
from restkit.config import Settings
from restkit.contracts import Error, assert_contract, assert_status

pytestmark = [allure.epic("REST API"), allure.feature("Authentication")]


@pytest.mark.negative
@pytest.mark.parametrize("token", [None, "invalid-token"])
def test_protected_endpoint_requires_valid_token(settings: Settings, token: str | None) -> None:
    config = settings.model_copy(update={"token": SecretStr(token) if token else None})
    with ApiClient(config) as client:
        response = client.request("GET", "users")
    assert_status(response, 401)
    assert response.headers["www-authenticate"] == "Bearer"
    assert_contract(response, Error)


@pytest.mark.demo
@pytest.mark.smoke
def test_login_returns_bearer_token(settings: Settings) -> None:
    with ApiClient(settings) as client:
        response = client.request(
            "POST", "auth/token", json={"username": "demo", "password": "demo"}
        )
    assert_status(response, 200)
    assert response.json()["access_token"]
    assert response.json()["token_type"] == "bearer"


@pytest.mark.demo
@pytest.mark.negative
def test_invalid_credentials_rejected(settings: Settings) -> None:
    with ApiClient(settings) as client:
        response = client.request(
            "POST", "auth/token", json={"username": "demo", "password": "wrong"}
        )
    assert_status(response, 401)
    assert assert_contract(response, Error).detail == "Invalid credentials"
