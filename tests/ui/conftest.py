import logging
import os
import re
from collections.abc import Callable, Generator, Iterator
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

from restkit.ui.pages import LoginPage, UsersPage

logger = logging.getLogger(__name__)


@pytest.fixture
def browser_factory(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[], WebDriver]]:
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

    drivers: list[WebDriver] = []

    def create() -> WebDriver:
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
        # Register before initialization so a timeout-setting error cannot leak the process.
        drivers.append(driver)
        # Mixing implicit and explicit waits makes timeout durations unpredictable.
        driver.implicitly_wait(0)
        driver.set_page_load_timeout(15)
        driver.set_script_timeout(10)
        return driver

    try:
        yield create
    finally:
        failures = []
        for driver in reversed(drivers):
            try:
                driver.quit()
            except Exception as exc:
                # Try every owned browser; one broken session must not leak the remaining ones.
                failures.append(type(exc).__name__)
        assert not failures, f"Browser cleanup failed: {failures}"


@pytest.fixture
def browser(browser_factory: Callable[[], WebDriver]) -> WebDriver:
    return browser_factory()


@pytest.fixture
def second_browser(browser_factory: Callable[[], WebDriver]) -> WebDriver:
    return browser_factory()


@pytest.fixture
def login_page(browser: WebDriver, demo_url: str) -> LoginPage:
    return LoginPage(browser).open(demo_url)


@pytest.fixture
def users_page(login_page: LoginPage) -> UsersPage:
    return login_page.sign_in()


@pytest.fixture
def ui_payload(owned_payloads: Callable[..., dict[str, Any]]) -> dict[str, Any]:
    return owned_payloads()


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if report.failed and report.when in {"setup", "call"} and isinstance(item, pytest.Function):
        for browser_name in ("browser", "second_browser"):
            driver = item.funcargs.get(browser_name)
            if not isinstance(driver, WebDriver):
                continue
            try:
                name = re.sub(r"[^A-Za-z0-9_.-]", "_", item.nodeid)[:120]
                name += f"-{browser_name}-{uuid4().hex[:8]}"
                output = Path("reports/ui/screenshots")
                output.mkdir(parents=True, exist_ok=True)
                screenshot = driver.get_screenshot_as_png()
                (output / f"{name}.png").write_bytes(screenshot)
                allure.attach(
                    screenshot,
                    name=f"UI failure ({browser_name})",
                    attachment_type=allure.attachment_type.PNG,
                )
                allure.attach(
                    driver.page_source,
                    name=f"Page DOM ({browser_name})",
                    attachment_type=allure.attachment_type.HTML,
                )
            except (WebDriverException, OSError) as exc:
                # Diagnostics must never replace the assertion that actually caused the failure.
                logger.warning("Could not capture UI diagnostics: %s", type(exc).__name__)
    return report
