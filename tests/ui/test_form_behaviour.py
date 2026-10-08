from collections.abc import Callable
from dataclasses import replace

import allure
import pytest

from restkit.apis.users import UsersApi
from restkit.contracts import User
from restkit.ui.models import UserDraft
from restkit.ui.pages import LoginPage, UsersPage
from tests.helpers import read_all_users, read_user

pytestmark = [
    pytest.mark.ui,
    pytest.mark.demo,
    pytest.mark.advanced,
    allure.epic("UI"),
    allure.feature("Формы и клавиатура"),
]


@pytest.mark.negative
@pytest.mark.parametrize("field", ["name", "email"])
def test_required_create_field_preserves_other_values_until_corrected(
    users_page: UsersPage, user_data: UserDraft, users: UsersApi, field: str
) -> None:
    before = read_all_users(users)
    complete = replace(user_data, role="admin")
    incomplete = replace(complete, **{field: ""})
    users_page.fill_create_form(incomplete.name, incomplete.email, incomplete.role)
    users_page.submit_create()

    assert users_page.validation_message(f"new-{field}")
    assert users_page.create_form == incomplete
    assert read_all_users(users) == before

    users_page.create_user(complete.name, complete.email, complete.role)
    users_page.wait_for_notice("User created")
    saved = read_user(users, users_page.user(complete.email).id)
    assert (saved.name, saved.email, saved.role) == (complete.name, complete.email, complete.role)
    assert read_all_users(users) == before + [saved]


def test_create_name_is_limited_by_browser_before_request(
    users_page: UsersPage, user_data: UserDraft, users: UsersApi
) -> None:
    expected_name = "x" * 100
    # Проверяем реальный ввод: браузер должен ограничить поле до отправки запроса серверу.
    users_page.fill_create_form(expected_name + "extra", user_data.email)
    assert users_page.create_form == replace(user_data, name=expected_name)
    users_page.submit_create()
    users_page.wait_for_notice("User created")
    saved = read_user(users, users_page.user(user_data.email).id)
    assert saved.name == expected_name
    assert saved.email == user_data.email


def test_edit_name_is_limited_without_changing_user_identity(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user(role="admin")
    expected_name = "y" * 100
    users_page.refresh()
    users_page.start_edit(str(original.email))
    users_page.submit_edit(expected_name + "extra")
    users_page.wait_for_notice("User updated")
    assert not users_page.editing
    assert users_page.user(str(original.email)).name == expected_name
    assert read_user(users, original.id) == original.model_copy(update={"name": expected_name})


def test_successful_create_resets_fields_and_default_role(
    users_page: UsersPage,
    user_data: UserDraft,
    user_drafts: Callable[..., UserDraft],
    users: UsersApi,
) -> None:
    admin = user_drafts(role="admin")
    users_page.create_user(admin.name, admin.email, admin.role)
    users_page.wait_for_notice("User created")
    assert users_page.create_form == UserDraft("", "")
    assert users_page.user(admin.email).role == "admin"

    users_page.create_user(user_data.name, user_data.email)
    users_page.wait_for_notice("User created")
    assert users_page.create_form == UserDraft("", "")
    assert read_user(users, users_page.user(user_data.email).id).role == "user"
    assert read_user(users, users_page.user(admin.email).id).role == "admin"
    assert set(users_page.emails) == {admin.email, user_data.email}


def test_login_create_and_edit_can_be_submitted_with_enter(
    login_page: LoginPage, user_data: UserDraft, users: UsersApi
) -> None:
    with allure.step("Войти и создать пользователя клавишей Enter"):
        page = login_page.sign_in(by_enter=True)
        page.fill_create_form(user_data.name, user_data.email)
        page.submit_create(by_enter=True)
        page.wait_for_notice("User created")
        row = page.user(user_data.email)
        original = read_user(users, row.id)
        assert (original.name, original.email) == (user_data.name, user_data.email)

    with allure.step("Сохранить редактирование клавишей Enter"):
        page.start_edit(user_data.email)
        page.submit_edit("Имя изменено с клавиатуры", by_enter=True)
        page.wait_for_notice("User updated")
        assert not page.editing
        assert page.user(user_data.email).name == "Имя изменено с клавиатуры"
        assert read_user(users, row.id) == original.model_copy(
            update={"name": "Имя изменено с клавиатуры"}
        )


@pytest.mark.negative
def test_empty_edit_is_blocked_and_can_be_corrected_in_same_form(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user()
    users_page.refresh()
    users_page.start_edit(str(original.email))
    users_page.submit_edit("")
    assert users_page.validation_message("edit-name")
    assert users_page.editing
    assert users_page.edit_name == ""
    assert read_user(users, original.id) == original

    users_page.submit_edit("Исправленное имя")
    users_page.wait_for_notice("User updated")
    assert not users_page.editing
    assert read_user(users, original.id) == original.model_copy(update={"name": "Исправленное имя"})
