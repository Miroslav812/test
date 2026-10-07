import logging
import os
import re
from collections.abc import Generator, Iterator
from pathlib import Path
from typing import Any
from uuid import uuid4

import allure
import pytest
from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chromium.options import ChromiumOptions
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.remote.webdriver import WebDriver

from restkit.apis.users import UsersApi
from restkit.contracts import UserPage, assert_contract, assert_status
from restkit.ui.pages import LoginPage, UsersPage
from tests.factories import user_payload

logger = logging.getLogger(__name__)


@pytest.fixture
def browser(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> Iterator[WebDriver]:
    config = request.config
    binary = config.getoption("--browser-binary") or os.getenv("UI_BROWSER_BINARY")
    driver_path = config.getoption("--driver-path") or os.getenv("UI_DRIVER_PATH")
    if driver_path and not Path(driver_path).is_file():
        raise pytest.UsageError(
            "--driver-path / UI_DRIVER_PATH must point to a WebDriver executable"
        )

    # WebDriver talks to localhost, even when the machine uses a proxy for Internet access.
    monkeypatch.setenv(
        "NO_PROXY", ",".join(filter(None, [os.getenv("NO_PROXY"), "localhost", "127.0.0.1"]))
    )

    def configure(options: ChromiumOptions) -> None:
        if not config.getoption("--headed"):
            options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1000")
        options.add_argument("--disable-dev-shm-usage")
        if config.getoption("--browser-no-sandbox"):
            options.add_argument("--no-sandbox")
        if binary:
            options.binary_location = binary

    if config.getoption("--browser") == "edge":
        edge_options = EdgeOptions()
        configure(edge_options)
        driver: WebDriver = webdriver.Edge(
            service=EdgeService(executable_path=driver_path), options=edge_options
        )
    else:
        chrome_options = ChromeOptions()
        configure(chrome_options)
        driver = webdriver.Chrome(
            service=ChromeService(executable_path=driver_path), options=chrome_options
        )
    try:
        # Mixing implicit and explicit waits makes timeout durations unpredictable.
        driver.implicitly_wait(0)
        driver.set_page_load_timeout(15)
        driver.set_script_timeout(10)
        yield driver
    finally:
        driver.quit()


@pytest.fixture
def login_page(browser: WebDriver, demo_url: str) -> LoginPage:
    return LoginPage(browser).open(demo_url)


@pytest.fixture
def users_page(login_page: LoginPage) -> UsersPage:
    return login_page.sign_in()


@pytest.fixture
def ui_payload(users: UsersApi) -> Iterator[dict[str, Any]]:
    payload = user_payload()
    yield payload
    # UI-created records may exist even if the assertion failed before an ID could be captured.
    # Match only the unique email owned by this test; never reset the shared application store.
    offset = 0
    owned_ids: list[str] = []
    while True:
        response = users.list(limit=100, offset=offset)
        assert_status(response, 200)
        page = assert_contract(response, UserPage)
        owned_ids.extend(str(user.id) for user in page.items if user.email == payload["email"])
        offset += len(page.items)
        if not page.items or offset >= page.total:
            break
    failures = []
    for identifier in owned_ids:
        response = users.delete(identifier)
        if response.status_code not in {204, 404}:
            failures.append(response.status_code)
    assert not failures, f"UI test data cleanup failed: {failures}"


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    driver = item.funcargs.get("browser") if isinstance(item, pytest.Function) else None
    if report.failed and report.when in {"setup", "call"} and isinstance(driver, WebDriver):
        try:
            name = re.sub(r"[^A-Za-z0-9_.-]", "_", item.nodeid)[:140] + f"-{uuid4().hex[:8]}"
            output = Path("reports/ui/screenshots")
            output.mkdir(parents=True, exist_ok=True)
            screenshot = driver.get_screenshot_as_png()
            (output / f"{name}.png").write_bytes(screenshot)
            allure.attach(screenshot, name="UI failure", attachment_type=allure.attachment_type.PNG)
            allure.attach(
                driver.page_source, name="Page DOM", attachment_type=allure.attachment_type.HTML
            )
        except (WebDriverException, OSError) as exc:
            # Diagnostics must never replace the assertion that actually caused the failure.
            logger.warning("Could not capture UI diagnostics: %s", type(exc).__name__)
    return report
