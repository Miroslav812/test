from dataclasses import dataclass
from typing import Literal

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait


def test_id(value: str) -> tuple[str, str]:
    """Selectors are an explicit UI contract, independent of styling and translated labels."""
    return By.CSS_SELECTOR, f'[data-testid="{value}"]'


class BasePage:
    def __init__(self, driver: WebDriver, timeout: float = 10) -> None:
        self.driver = driver
        # A redraw may detach a row between polls; retry the lookup, not the user action.
        self.wait = WebDriverWait(
            driver, timeout, ignored_exceptions=(StaleElementReferenceException,)
        )

    def _visible(self, identifier: str) -> WebElement:
        return self.wait.until(EC.visibility_of_element_located(test_id(identifier)))

    def _click(self, identifier: str) -> None:
        self.wait.until(EC.element_to_be_clickable(test_id(identifier))).click()

    def _fill(self, identifier: str, value: str) -> None:
        element = self._visible(identifier)
        # WebElement.clear() need not fire an input event. Keyboard edits keep reactive forms
        # in sync even when the target value is empty (for example, resetting a search filter).
        modifier = (
            Keys.COMMAND if self.driver.capabilities.get("platformName") == "mac" else Keys.CONTROL
        )
        element.send_keys(modifier, "a")
        element.send_keys(Keys.BACKSPACE)
        if value:
            element.send_keys(value)

    def validation_message(self, field: str) -> str:
        # Native validation messages are localized; tests assert presence rather than English text.
        return str(self._visible(field).get_property("validationMessage"))


class LoginPage(BasePage):
    def open(self, base_url: str) -> "LoginPage":
        self.driver.get(f"{base_url.rstrip('/')}/ui")
        self.wait_loaded()
        return self

    def wait_loaded(self) -> None:
        self._visible("login-panel")

    def submit_credentials(self, username: str, password: str) -> None:
        self._fill("username", username)
        self._fill("password", password)
        self._click("sign-in")

    def sign_in(self, username: str = "demo", password: str = "demo") -> "UsersPage":
        self.submit_credentials(username, password)
        page = UsersPage(self.driver)
        page.wait_loaded()
        return page

    @property
    def error_message(self) -> str:
        return self._visible("login-error").text


@dataclass(frozen=True)
class UserRow:
    id: str
    name: str
    email: str
    role: str


class UsersPage(BasePage):
    def wait_loaded(self) -> None:
        self._visible("dashboard")
        self.wait.until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, '[data-testid="users-body"][data-loaded="true"]')
            )
        )

    def refresh(self) -> None:
        self._click("refresh-users")
        self.wait_loaded()

    def create_user(self, name: str, email: str, role: str = "user") -> None:
        self._fill("new-name", name)
        self._fill("new-email", email)
        Select(self._visible("new-role")).select_by_value(role)
        self._click("create-user")

    def _row(self, email: str) -> WebElement:
        def find(driver: WebDriver) -> WebElement | Literal[False]:
            for row in driver.find_elements(*test_id("user-row")):
                if row.find_element(*test_id("user-email")).text == email:
                    return row
            return False

        return self.wait.until(find)

    def user(self, email: str) -> UserRow:
        row = self._row(email)
        return UserRow(
            id=str(row.get_attribute("data-user-id")),
            name=row.find_element(*test_id("user-name")).text,
            email=row.find_element(*test_id("user-email")).text,
            role=row.find_element(*test_id("user-role")).text,
        )

    def edit_user(self, email: str, name: str) -> None:
        self.start_edit(email)
        self.submit_edit(name)
        self.wait_for_notice("User updated")

    def start_edit(self, email: str) -> None:
        self._row(email).find_element(*test_id("edit-user")).click()

    def submit_edit(self, name: str) -> None:
        self.change_edit_name(name)
        self._click("save-user")

    def change_edit_name(self, name: str) -> None:
        self._fill("edit-name", name)

    def cancel_edit(self) -> None:
        self._click("cancel-edit")
        self.wait.until(EC.invisibility_of_element_located(test_id("edit-form")))

    def wait_for_notice(self, message: str) -> None:
        self.wait.until(EC.text_to_be_present_in_element(test_id("user-notice"), message))
        self._visible("user-notice")

    def delete_user(self, email: str) -> None:
        row = self._row(email)
        identifier = row.get_attribute("data-user-id")
        row.find_element(*test_id("delete-user")).click()
        self.wait.until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, f'[data-user-id="{identifier}"]'))
        )
        self.wait.until(EC.text_to_be_present_in_element(test_id("user-notice"), "User deleted"))

    def search(self, query: str) -> None:
        self._fill("search", query)

    @property
    def emails(self) -> list[str]:
        return [cell.text for cell in self.driver.find_elements(*test_id("user-email"))]

    @property
    def error_message(self) -> str:
        return self._visible("user-error").text

    @property
    def error_visible(self) -> bool:
        return self.driver.find_element(*test_id("user-error")).is_displayed()

    @property
    def empty_message(self) -> str:
        return self._visible("empty-state").text

    def embedded_images(self, email: str) -> int:
        return len(
            self._row(email).find_element(*test_id("user-name")).find_elements(By.TAG_NAME, "img")
        )

    def sign_out(self) -> LoginPage:
        self._click("logout")
        login = LoginPage(self.driver)
        login.wait_loaded()
        return login
