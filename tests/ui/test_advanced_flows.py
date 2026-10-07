from collections.abc import Callable
from typing import Any

import allure
import pytest
from selenium.webdriver.remote.webdriver import WebDriver

from restkit.apis.users import UsersApi
from restkit.contracts import User, assert_contract, assert_status
from restkit.ui.pages import LoginPage, UsersPage
from tests.helpers import read_all_users

pytestmark = [
    pytest.mark.ui,
    pytest.mark.demo,
    pytest.mark.advanced,
    allure.epic("UI"),
    allure.feature("Recovery and multiple sessions"),
]


@pytest.mark.negative
def test_invalid_email_can_be_corrected_without_creating_bad_data(
    users_page: UsersPage, ui_payload: dict[str, Any], users: UsersApi
) -> None:
    before = read_all_users(users)
    users_page.create_user(ui_payload["name"], "not-an-email")
    assert users_page.validation_message("new-email")
    assert read_all_users(users) == before
    users_page.create_user(ui_payload["name"], ui_payload["email"])
    row = users_page.user(ui_payload["email"])
    assert row.name == ui_payload["name"]
    assert len(read_all_users(users)) == len(before) + 1


@pytest.mark.negative
def test_server_validation_error_can_be_corrected_in_same_editor(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user()
    users_page.refresh()
    users_page.start_edit(str(original.email))
    # Spaces satisfy HTML's required attribute but must still be rejected by server validation.
    users_page.submit_edit("   ")
    assert users_page.error_message == "Invalid input"
    assert assert_contract(users.get(str(original.id)), User) == original
    users_page.submit_edit("Recovered edit")
    users_page.wait_for_notice("User updated")
    assert not users_page.error_visible
    assert users_page.user(str(original.email)).name == "Recovered edit"
    assert assert_contract(users.get(str(original.id)), User) == original.model_copy(
        update={"name": "Recovered edit"}
    )


def test_cancel_edit_does_not_persist_changes(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    original = create_user()
    users_page.refresh()
    users_page.start_edit(str(original.email))
    # Edit the field through keyboard events, then cancel without submitting the form.
    # The field is deliberately accessed through the page operation rather than raw JS.
    users_page.change_edit_name("Cancelled change")
    users_page.cancel_edit()
    assert users_page.user(str(original.email)).name == original.name
    assert assert_contract(users.get(str(original.id)), User) == original
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
    ui_payload: dict[str, Any],
    users: UsersApi,
) -> None:
    second = LoginPage(second_browser).open(demo_url).sign_in()
    with allure.step("Session B creates a user; session A refreshes and sees it"):
        second.create_user(ui_payload["name"], ui_payload["email"])
        row = second.user(ui_payload["email"])
        users_page.refresh()
        assert users_page.user(ui_payload["email"]) == row
    with allure.step("Session A edits; session B sees the persisted change"):
        users_page.edit_user(ui_payload["email"], "Edited in session A")
        second.refresh()
        assert second.user(ui_payload["email"]).name == "Edited in session A"
        assert assert_contract(users.get(row.id), User).name == "Edited in session A"
    with allure.step("Signing out A must not invalidate B; B can still delete the user"):
        signed_out = users_page.sign_out()
        second.delete_user(ui_payload["email"])
        assert_status(users.get(row.id), 404)
        # Verify the new login has fresh data rather than the signed-out session's cached row.
        reconnected = signed_out.sign_in()
        assert ui_payload["email"] not in reconnected.emails


@pytest.mark.resilience
def test_network_failure_is_recoverable_without_duplicate_creation(
    users_page: UsersPage, browser: WebDriver, ui_payload: dict[str, Any], users: UsersApi
) -> None:
    before = read_all_users(users)
    browser.execute_cdp_cmd("Network.enable", {})
    conditions = {"offline": True, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1}
    browser.execute_cdp_cmd("Network.emulateNetworkConditions", conditions)
    try:
        with allure.step("Lose the browser network and verify that no record is persisted"):
            users_page.create_user(ui_payload["name"], ui_payload["email"])
            assert users_page.error_message
            assert read_all_users(users) == before
    finally:
        # Only the browser is offline; the API observer and fixture cleanup remain connected.
        # Restore connectivity even when the failure assertion raises.
        browser.execute_cdp_cmd(
            "Network.emulateNetworkConditions", {**conditions, "offline": False}
        )
    with allure.step("Restore connectivity and retry the user action once"):
        users_page.create_user(ui_payload["name"], ui_payload["email"])
        row = users_page.user(ui_payload["email"])
        assert not users_page.error_visible
        saved = [user for user in read_all_users(users) if user.email == ui_payload["email"]]
        assert len(saved) == 1
        assert str(saved[0].id) == row.id


def test_ui_lists_and_searches_records_beyond_first_api_page(
    users_page: UsersPage, create_user: Callable[..., User], users: UsersApi
) -> None:
    # 102 crosses the API's 100-record page limit; a UI fetching only page one loses the tail.
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
    owned_payloads: Callable[..., dict[str, Any]],
    create_user: Callable[..., User],
    users: UsersApi,
) -> None:
    duplicate, recovery = owned_payloads(), owned_payloads()
    existing = create_user(email=duplicate["email"])
    users_page.refresh()
    users_page.create_user("Rejected duplicate", str(existing.email))
    assert users_page.error_message == "Email already exists"
    assert assert_contract(users.get(str(existing.id)), User) == existing
    users_page.create_user(recovery["name"], recovery["email"])
    assert users_page.user(recovery["email"]).name == recovery["name"]
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
    assert assert_contract(users.get(str(original.id)), User) == original
