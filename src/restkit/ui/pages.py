from typing import Literal

from selenium.common.exceptions import StaleElementReferenceException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.select import Select
from selenium.webdriver.support.ui import WebDriverWait

from restkit.ui.models import UserDraft, UserRow


def test_id(value: str) -> tuple[str, str]:
    """Ищем элементы по устойчивому контракту, независимо от CSS и языка интерфейса."""
    return By.CSS_SELECTOR, f'[data-testid="{value}"]'


class BasePage:
    def __init__(self, driver: WebDriver, timeout: float = 10) -> None:
        self.driver = driver
        # После перерисовки повторяем поиск элемента; сам клик повторять небезопасно.
        self.wait = WebDriverWait(
            driver, timeout, ignored_exceptions=(StaleElementReferenceException,)
        )

    def _visible(self, identifier: str) -> WebElement:
        return self.wait.until(EC.visibility_of_element_located(test_id(identifier)))

    def _click(self, identifier: str) -> None:
        self.wait.until(EC.element_to_be_clickable(test_id(identifier))).click()

    def _fill(self, identifier: str, value: str) -> None:
        element = self._visible(identifier)
        # clear() не всегда вызывает input. Клавиатура обновляет форму и при очистке поиска.
        modifier = (
            Keys.COMMAND if self.driver.capabilities.get("platformName") == "mac" else Keys.CONTROL
        )
        element.send_keys(modifier, "a")
        element.send_keys(Keys.BACKSPACE)
        if value:
            element.send_keys(value)

    def validation_message(self, field: str) -> str:
        # Текст зависит от языка браузера: в тестах проверяем наличие сообщения.
        return str(self._visible(field).get_property("validationMessage"))

    def _value(self, identifier: str) -> str:
        return str(self._visible(identifier).get_property("value"))

    def _is_visible(self, identifier: str) -> bool:
        return self.driver.find_element(*test_id(identifier)).is_displayed()

    def _submit(self, button: str, field: str, *, by_enter: bool) -> None:
        if by_enter:
            self._visible(field).send_keys(Keys.ENTER)
        else:
            self._click(button)


class LoginPage(BasePage):
    def open(self, base_url: str) -> "LoginPage":
        self.driver.get(f"{base_url.rstrip('/')}/ui")
        self.wait_loaded()
        return self

    def wait_loaded(self) -> None:
        self._visible("login-panel")

    def reload(self) -> "LoginPage":
        self.driver.refresh()
        self.wait_loaded()
        return self

    def submit_credentials(self, username: str, password: str, *, by_enter: bool = False) -> None:
        self._fill("username", username)
        self._fill("password", password)
        self._submit("sign-in", "password", by_enter=by_enter)

    def sign_in(
        self, username: str = "demo", password: str = "demo", *, by_enter: bool = False
    ) -> "UsersPage":
        self.submit_credentials(username, password, by_enter=by_enter)
        page = UsersPage(self.driver)
        page.wait_loaded()
        return page

    @property
    def error_message(self) -> str:
        return self._visible("login-error").text

    @property
    def error_visible(self) -> bool:
        return self._is_visible("login-error")

    @property
    def username(self) -> str:
        return self._value("username")

    @property
    def password(self) -> str:
        return self._value("password")


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
        self.fill_create_form(name, email, role)
        self.submit_create()

    def fill_create_form(self, name: str, email: str, role: str = "user") -> None:
        self._fill("new-name", name)
        self._fill("new-email", email)
        Select(self._visible("new-role")).select_by_value(role)

    def submit_create(self, *, by_enter: bool = False) -> None:
        self._submit("create-user", "new-email", by_enter=by_enter)

    @property
    def create_form(self) -> UserDraft:
        return UserDraft(self._value("new-name"), self._value("new-email"), self._value("new-role"))

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
        self._visible("edit-form")

    def submit_edit(self, name: str, *, by_enter: bool = False) -> None:
        self.change_edit_name(name)
        self._submit("save-user", "edit-name", by_enter=by_enter)

    def change_edit_name(self, name: str) -> None:
        self._fill("edit-name", name)

    def cancel_edit(self) -> None:
        self._click("cancel-edit")
        self.wait.until(EC.invisibility_of_element_located(test_id("edit-form")))

    @property
    def editing(self) -> bool:
        return self._is_visible("edit-form")

    @property
    def edit_name(self) -> str:
        return self._value("edit-name")

    def wait_for_notice(self, message: str) -> None:
        self.wait.until(EC.text_to_be_present_in_element(test_id("user-notice"), message))
        self._visible("user-notice")

    def delete_user(self, email: str) -> None:
        identifier = self.submit_delete(email)
        self.wait.until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, f'[data-user-id="{identifier}"]'))
        )
        self.wait_for_notice("User deleted")

    def submit_delete(self, email: str) -> str:
        row = self._row(email)
        identifier = str(row.get_attribute("data-user-id"))
        row.find_element(*test_id("delete-user")).click()
        return identifier

    def search(self, query: str) -> None:
        self._fill("search", query)

    @property
    def search_query(self) -> str:
        return self._value("search")

    @property
    def emails(self) -> list[str]:
        return [cell.text for cell in self.driver.find_elements(*test_id("user-email"))]

    @property
    def error_message(self) -> str:
        return self._visible("user-error").text

    @property
    def error_visible(self) -> bool:
        return self._is_visible("user-error")

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
