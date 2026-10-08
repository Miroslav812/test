from collections.abc import Callable
from dataclasses import replace

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
    allure.feature("Редактор, фильтры и границы сессии"),
]


def test_switching_editor_discards_previous_unsaved_draft(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    first, second = create_user(), create_user(role="admin")
    users_page.refresh()
    users_page.start_edit(str(first.email))
    users_page.change_edit_name("Несохранённый черновик")
    users_page.start_edit(str(second.email))
    assert users_page.edit_name == second.name

    users_page.submit_edit("Изменён только второй")
    users_page.wait_for_notice("User updated")
    assert not users_page.editing
    assert read_user(users, first.id) == first
    assert read_user(users, second.id) == second.model_copy(
        update={"name": "Изменён только второй"}
    )
    users_page.refresh()
    assert users_page.user(str(first.email)).name == first.name
    assert users_page.user(str(second.email)).name == "Изменён только второй"


def test_editing_name_reapplies_active_filter_without_deleting_data(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user(name="Filter target", role="admin")
    other = create_user(name="Untouched record")
    users_page.refresh()
    users_page.search("TARGET")
    assert users_page.emails == [str(original.email)]

    users_page.edit_user(str(original.email), "Outside filter")
    assert users_page.search_query == "TARGET"
    assert users_page.emails == []
    assert users_page.empty_message == "No users match your search."
    assert read_user(users, original.id) == original.model_copy(update={"name": "Outside filter"})
    assert read_user(users, other.id) == other
    users_page.search("")
    assert set(users_page.emails) == {str(original.email), str(other.email)}


def test_refresh_keeps_filter_and_applies_external_changes(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user(name="Team initial")
    other = create_user(name="Other group")
    users_page.refresh()
    users_page.search("TEAM")
    assert users_page.emails == [str(original.email)]

    with allure.step("Другой клиент изменяет запись и добавляет новую"):
        assert_status(users.update(str(original.id), {"name": "Moved elsewhere"}), 200)
        incoming = create_user(name="Team incoming")
    with allure.step("Обновить список, сохранив фильтр"):
        users_page.refresh()
        assert users_page.search_query == "TEAM"
        assert users_page.emails == [str(incoming.email)]
        assert read_user(users, original.id) == original.model_copy(
            update={"name": "Moved elsewhere"}
        )
        assert read_user(users, other.id) == other
    users_page.search("")
    assert set(users_page.emails) == {str(original.email), str(other.email), str(incoming.email)}


def test_deleting_edited_user_closes_form_without_touching_another_record(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original, other = create_user(), create_user()
    users_page.refresh()
    users_page.start_edit(str(original.email))
    users_page.change_edit_name("Черновик перед удалением")
    users_page.delete_user(str(original.email))

    assert not users_page.editing
    assert users_page.emails == [str(other.email)]
    assert_status(users.get(str(original.id)), 404)
    assert read_user(users, other.id) == other
    users_page.refresh()
    assert not users_page.editing
    assert users_page.user(str(other.email)).name == other.name


@pytest.mark.negative
def test_stale_delete_reports_error_and_allows_next_action(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original, other = create_user(), create_user()
    users_page.refresh()
    assert_status(users.delete(str(original.id)), 204)
    # Строка ещё видна в браузере, хотя другой клиент уже удалил её на сервере.
    users_page.submit_delete(str(original.email))
    assert users_page.error_message == "User not found"
    assert_status(users.get(str(original.id)), 404)
    assert read_user(users, other.id) == other

    users_page.refresh()
    assert users_page.emails == [str(other.email)]
    users_page.delete_user(str(other.email))
    assert not users_page.error_visible
    assert read_all_users(users) == []


@pytest.mark.parametrize("exit_method", ["logout", "reload"])
def test_leaving_session_discards_drafts_but_keeps_saved_users(
    users_page: UsersPage,
    login_page: LoginPage,
    user_data: UserDraft,
    create_user: Callable[..., User],
    users: UsersApi,
    exit_method: str,
) -> None:
    original = create_user(role="admin")
    users_page.refresh()
    users_page.search(str(original.email))
    users_page.start_edit(str(original.email))
    users_page.submit_edit("   ")
    assert users_page.error_message == "Invalid input"
    users_page.change_edit_name("Несохранённое редактирование")
    users_page.fill_create_form(user_data.name, user_data.email, user_data.role)

    with allure.step("Завершить сессию с открытыми формами и сообщением об ошибке"):
        login = users_page.sign_out() if exit_method == "logout" else login_page.reload()
        assert login.username == login.password == ""
        assert not login.error_visible
    with allure.step("Повторный вход получает сохранённые данные без старых черновиков"):
        restored = login.sign_in()
        assert not restored.editing
        assert restored.create_form == UserDraft("", "")
        assert restored.search_query == ""
        assert not restored.error_visible
        assert restored.emails == [str(original.email)]
        assert read_user(users, original.id) == original
        assert read_all_users(users) == [original]


@pytest.mark.resilience
def test_offline_edit_preserves_draft_and_recovers_without_changing_identity(
    users_page: UsersPage, browser: WebDriver, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user(role="admin")
    name = "Сохранено после восстановления сети"
    users_page.refresh()
    users_page.start_edit(str(original.email))
    with allure.step("Потеря сети сохраняет черновик и не меняет запись"), offline_browser(browser):
        users_page.submit_edit(name)
        assert users_page.error_message
        assert users_page.editing
        assert users_page.edit_name == name
        assert read_all_users(users) == [original]

    with allure.step("Повторить сохранение в том же редакторе после восстановления сети"):
        users_page.submit_edit(name)
        users_page.wait_for_notice("User updated")
        assert not users_page.editing
        assert not users_page.error_visible
        assert users_page.user(str(original.email)).name == name
        assert read_all_users(users) == [original.model_copy(update={"name": name})]


@pytest.mark.negative
def test_two_sessions_resolve_duplicate_drafts_without_overwriting_winner(
    users_page: UsersPage,
    second_browser: WebDriver,
    demo_url: str,
    user_data: UserDraft,
    user_drafts: Callable[..., UserDraft],
    users: UsersApi,
) -> None:
    rejected = replace(user_data, name="Черновик первой сессии", role="admin")
    winner = replace(user_data, name="Запись второй сессии")
    recovery = user_drafts(name="Исправленная запись", role="admin")
    second = LoginPage(second_browser).open(demo_url).sign_in()
    users_page.fill_create_form(rejected.name, rejected.email, rejected.role)

    with allure.step("Вторая сессия первой сохраняет общий email"):
        second.create_user(winner.name, winner.email, winner.role)
        second.wait_for_notice("User created")
        row = second.user(winner.email)
        saved = read_user(users, row.id)
        assert (saved.name, saved.role) == (winner.name, winner.role)
    with allure.step("Конфликт не меняет сохранённую запись и не очищает черновик"):
        users_page.submit_create()
        assert users_page.error_message == "Email already exists"
        assert users_page.create_form == rejected
        assert read_all_users(users) == [saved]
    with allure.step("Исправить email и синхронизировать результат в обоих браузерах"):
        users_page.create_user(recovery.name, recovery.email, recovery.role)
        users_page.wait_for_notice("User created")
        recovered_row = users_page.user(recovery.email)
        recovered = read_user(users, recovered_row.id)
        assert (recovered.name, recovered.role) == (recovery.name, recovery.role)
        assert not users_page.error_visible
        assert read_all_users(users) == [saved, recovered]
        second.refresh()
        assert second.user(winner.email) == row
        assert second.user(recovery.email) == recovered_row
