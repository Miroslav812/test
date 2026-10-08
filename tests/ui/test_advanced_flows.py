from collections.abc import Callable

import allure
import pytest
from selenium.webdriver.remote.webdriver import WebDriver

from restkit.apis.users import UsersApi
from restkit.contracts import User, assert_status
from restkit.ui.models import UserDraft
from restkit.ui.pages import LoginPage, UsersPage
from tests.helpers import read_all_users, read_user
from tests.ui.network import offline_browser

pytestmark = [
    pytest.mark.ui,
    pytest.mark.demo,
    pytest.mark.advanced,
    allure.epic("UI"),
    allure.feature("Восстановление и взаимодействие сессий"),
]


@pytest.mark.negative
def test_invalid_email_can_be_corrected_without_creating_bad_data(
    users_page: UsersPage, user_data: UserDraft, users: UsersApi
) -> None:
    before = read_all_users(users)
    users_page.create_user(user_data.name, "not-an-email")
    assert users_page.validation_message("new-email")
    assert read_all_users(users) == before
    users_page.create_user(user_data.name, user_data.email)
    row = users_page.user(user_data.email)
    assert row.name == user_data.name
    assert len(read_all_users(users)) == len(before) + 1


@pytest.mark.negative
def test_server_validation_error_can_be_corrected_in_same_editor(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user()
    users_page.refresh()
    users_page.start_edit(str(original.email))
    # required пропускает пробелы, поэтому такой ввод должен отклонить сервер.
    users_page.submit_edit("   ")
    assert users_page.error_message == "Invalid input"
    assert read_user(users, original.id) == original
    users_page.submit_edit("Recovered edit")
    users_page.wait_for_notice("User updated")
    assert not users_page.error_visible
    assert users_page.user(str(original.email)).name == "Recovered edit"
    assert read_user(users, original.id) == original.model_copy(update={"name": "Recovered edit"})


def test_cancel_edit_does_not_persist_changes(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user()
    users_page.refresh()
    users_page.start_edit(str(original.email))
    users_page.change_edit_name("Cancelled change")
    users_page.cancel_edit()
    assert users_page.user(str(original.email)).name == original.name
    assert read_user(users, original.id) == original
    users_page.refresh()
    assert users_page.user(str(original.email)).name == original.name


@pytest.mark.negative
def test_editing_record_deleted_by_another_client_does_not_resurrect_it(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user()
    users_page.refresh()
    users_page.start_edit(str(original.email))
    assert_status(users.delete(str(original.id)), 204)
    users_page.submit_edit("Stale update")
    assert users_page.error_message == "User not found"
    assert_status(users.get(str(original.id)), 404)
    users_page.cancel_edit()
    users_page.refresh()
    assert str(original.email) not in users_page.emails


def test_two_browser_sessions_share_data_but_not_logout_state(
    users_page: UsersPage,
    second_browser: WebDriver,
    demo_url: str,
    user_data: UserDraft,
    users: UsersApi,
) -> None:
    second = LoginPage(second_browser).open(demo_url).sign_in()
    with allure.step("Вторая сессия создаёт запись; первая видит её после обновления"):
        second.create_user(user_data.name, user_data.email)
        row = second.user(user_data.email)
        users_page.refresh()
        assert users_page.user(user_data.email) == row
    with allure.step("Первая сессия меняет имя; вторая видит сохранённое изменение"):
        users_page.edit_user(user_data.email, "Edited in session A")
        second.refresh()
        assert second.user(user_data.email).name == "Edited in session A"
        assert read_user(users, row.id).name == "Edited in session A"
    with allure.step("Выход из первой сессии не мешает второй удалить запись"):
        signed_out = users_page.sign_out()
        second.delete_user(user_data.email)
        assert_status(users.get(row.id), 404)
        # Повторный вход должен получить свежие данные, а не строку из старого списка.
        reconnected = signed_out.sign_in()
        assert user_data.email not in reconnected.emails


@pytest.mark.resilience
def test_network_failure_is_recoverable_without_duplicate_creation(
    users_page: UsersPage, browser: WebDriver, user_data: UserDraft, users: UsersApi
) -> None:
    before = read_all_users(users)
    with allure.step("Потеря сети не должна создать запись"), offline_browser(browser):
        users_page.create_user(user_data.name, user_data.email)
        assert users_page.error_message
        assert users_page.create_form == user_data
        assert read_all_users(users) == before
    with allure.step("После восстановления сети повторить создание один раз"):
        users_page.create_user(user_data.name, user_data.email)
        row = users_page.user(user_data.email)
        assert not users_page.error_visible
        saved = [user for user in read_all_users(users) if user.email == user_data.email]
        assert len(saved) == 1
        assert str(saved[0].id) == row.id


def test_ui_lists_and_searches_records_beyond_first_api_page(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    # 102 записи пересекают границу API-страницы: загрузка только первой потеряет конец списка.
    batch = [create_user(name=f"Pagination user {index:03d}") for index in range(102)]
    users_page.refresh()
    assert users_page.emails == [str(user.email) for user in batch]
    last = batch[-1]
    users_page.search(str(last.email))
    assert users_page.emails == [str(last.email)]
    users_page.delete_user(str(last.email))
    assert_status(users.get(str(last.id)), 404)
    assert users_page.emails == []
    users_page.search("")
    assert users_page.emails == [str(user.email) for user in batch[:-1]]


def test_unicode_search_does_not_interpret_names_as_markup(
    users_page: UsersPage, create_user: Callable[..., User]
) -> None:
    name = "О'Коннор & <b>QA</b> 用户"
    original = create_user(name=name)
    create_user(name="Unrelated record")
    users_page.refresh()
    users_page.search("О'КОННОР")
    assert users_page.emails == [str(original.email)]
    assert users_page.user(str(original.email)).name == name


@pytest.mark.negative
def test_duplicate_error_is_cleared_after_valid_retry(
    users_page: UsersPage,
    user_drafts: Callable[..., UserDraft],
    create_user: Callable[..., User],
    users: UsersApi,
) -> None:
    duplicate, recovery = user_drafts(), user_drafts()
    existing = create_user(email=duplicate.email)
    users_page.refresh()
    users_page.create_user("Rejected duplicate", str(existing.email))
    assert users_page.error_message == "Email already exists"
    assert users_page.create_form == UserDraft("Rejected duplicate", duplicate.email)
    assert read_user(users, existing.id) == existing
    users_page.create_user(recovery.name, recovery.email)
    users_page.wait_for_notice("User created")
    assert users_page.user(recovery.email).name == recovery.name
    assert users_page.create_form == UserDraft("", "")
    assert not users_page.error_visible
    assert users_page.emails.count(str(existing.email)) == 1


def test_relogin_clears_previous_search_without_deleting_persisted_users(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user()
    users_page.refresh()
    users_page.search("no-such-record")
    assert users_page.emails == []
    reconnected = users_page.sign_out().sign_in()
    assert reconnected.user(str(original.email)).name == original.name
    assert read_user(users, original.id) == original
