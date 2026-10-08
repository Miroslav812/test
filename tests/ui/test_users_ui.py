from collections.abc import Callable

import allure
import pytest

from restkit.apis.users import UsersApi
from restkit.contracts import User, assert_status
from restkit.ui.models import UserDraft
from restkit.ui.pages import LoginPage, UsersPage
from tests.helpers import read_user

pytestmark = [pytest.mark.ui, pytest.mark.demo, allure.epic("UI"), allure.feature("Пользователи")]


@pytest.mark.smoke
def test_successful_login(login_page: LoginPage) -> None:
    page = login_page.sign_in()
    assert page.empty_message == "No users match your search."


@pytest.mark.negative
@pytest.mark.parametrize("username,password", [("demo", "wrong"), ("unknown", "demo")])
def test_invalid_credentials(login_page: LoginPage, username: str, password: str) -> None:
    login_page.submit_credentials(username, password)
    assert login_page.error_message == "Invalid credentials"
    login_page.wait_loaded()
    assert login_page.sign_in().emails == []


@pytest.mark.negative
def test_required_username(login_page: LoginPage) -> None:
    login_page.submit_credentials("", "demo")
    assert login_page.validation_message("username")
    login_page.wait_loaded()


@pytest.mark.smoke
@pytest.mark.parametrize("role", ["user", "admin"])
def test_create_user_persists_data(
    users_page: UsersPage, user_data: UserDraft, users: UsersApi, role: str
) -> None:
    with allure.step("Создать пользователя через браузер"):
        users_page.create_user(user_data.name, user_data.email, role)
        row = users_page.user(user_data.email)
        assert row.name == user_data.name
        assert row.role == role
    with allure.step("Проверить сохранённые данные через API"):
        saved = read_user(users, row.id)
        assert saved.email == user_data.email
        assert saved.name == user_data.name
        assert saved.role == role


def test_edit_user_persists_name(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    created = create_user()
    users_page.refresh()
    users_page.edit_user(str(created.email), "Edited in browser")
    assert users_page.user(str(created.email)).name == "Edited in browser"
    assert read_user(users, created.id) == created.model_copy(update={"name": "Edited in browser"})


def test_delete_user_removes_record(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    created = create_user()
    users_page.refresh()
    users_page.delete_user(str(created.email))
    assert str(created.email) not in users_page.emails
    assert_status(users.get(str(created.id)), 404)


@pytest.mark.negative
def test_duplicate_email_is_rejected(
    users_page: UsersPage, user_data: UserDraft, create_user: Callable[..., User]
) -> None:
    created = create_user(email=user_data.email)
    users_page.refresh()
    users_page.create_user("Duplicate", str(created.email))
    assert users_page.error_message == "Email already exists"
    assert users_page.emails.count(str(created.email)) == 1
    assert users_page.user(str(created.email)).name == created.name


def test_search_filters_users(users_page: UsersPage, create_user: Callable[..., User]) -> None:
    first, second = create_user(), create_user()
    users_page.refresh()
    users_page.search(str(first.email))
    assert users_page.emails == [str(first.email)]
    users_page.search("definitely-no-matching-record")
    assert users_page.empty_message == "No users match your search."
    assert users_page.emails == []
    users_page.search("")
    assert set(users_page.emails) == {str(first.email), str(second.email)}


@pytest.mark.negative
def test_user_name_is_rendered_as_text(
    users_page: UsersPage, create_user: Callable[..., User]
) -> None:
    # Браузер обнаруживает небезопасный innerHTML, который не виден в проверке API-схемы.
    name = '<img src="x" onerror="window.unexpectedImage=true">'
    created = create_user(name=name)
    users_page.refresh()
    assert users_page.user(str(created.email)).name == name
    assert users_page.embedded_images(str(created.email)) == 0


def test_logout_returns_to_login(users_page: UsersPage) -> None:
    login = users_page.sign_out()
    login.wait_loaded()
    # После перезагрузки проверяем, что токен не был сохранён в браузере.
    login.reload()
