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
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.edge.service import Service as EdgeService
from selenium.webdriver.remote.webdriver import WebDriver

from restkit.ui.models import UserDraft
from restkit.ui.pages import LoginPage, UsersPage

logger = logging.getLogger(__name__)


def _start_browser(config: pytest.Config) -> WebDriver:
    binary = config.getoption("--browser-binary") or os.getenv("UI_BROWSER_BINARY")
    driver_path = config.getoption("--driver-path") or os.getenv("UI_DRIVER_PATH")
    if driver_path and not Path(driver_path).is_file():
        raise pytest.UsageError(
            "--driver-path / UI_DRIVER_PATH must point to a WebDriver executable"
        )

    options = EdgeOptions() if config.getoption("--browser") == "edge" else ChromeOptions()
    if not config.getoption("--headed"):
        options.add_argument("--headless=new")
    options.add_argument("--window-size=1440,1000")
    options.add_argument("--disable-dev-shm-usage")
    if config.getoption("--browser-no-sandbox"):
        options.add_argument("--no-sandbox")
    if binary:
        options.binary_location = binary

    if isinstance(options, EdgeOptions):
        return webdriver.Edge(service=EdgeService(executable_path=driver_path), options=options)
    return webdriver.Chrome(service=ChromeService(executable_path=driver_path), options=options)


@pytest.fixture
def browser_factory(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> Iterator[Callable[[], WebDriver]]:
    # Драйвер работает через localhost, даже если для Интернета настроен прокси.
    monkeypatch.setenv(
        "NO_PROXY", ",".join(filter(None, [os.getenv("NO_PROXY"), "localhost", "127.0.0.1"]))
    )

    drivers: list[WebDriver] = []

    def create() -> WebDriver:
        driver = _start_browser(request.config)
        # Сразу запоминаем браузер: ошибка настройки таймаутов не должна оставить процесс.
        drivers.append(driver)
        # Не смешиваем implicit и explicit waits: иначе таймауты становятся непредсказуемыми.
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
                # Закрываем остальные сессии, даже если один драйвер уже перестал отвечать.
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
def user_drafts(owned_payloads: Callable[..., dict[str, Any]]) -> Callable[..., UserDraft]:
    def create(**fields: Any) -> UserDraft:
        return UserDraft(**owned_payloads(**fields))

    return create


@pytest.fixture
def user_data(user_drafts: Callable[..., UserDraft]) -> UserDraft:
    return user_drafts()


def _attach_browser_state(driver: WebDriver, browser_name: str, nodeid: str) -> None:
    try:
        name = re.sub(r"[^A-Za-z0-9_.-]", "_", nodeid)[:120]
        name += f"-{browser_name}-{uuid4().hex[:8]}"
        output = Path("reports/ui/screenshots")
        output.mkdir(parents=True, exist_ok=True)
        screenshot = driver.get_screenshot_as_png()
        (output / f"{name}.png").write_bytes(screenshot)
        allure.attach(
            screenshot,
            name=f"Снимок экрана ({browser_name})",
            attachment_type=allure.attachment_type.PNG,
        )
        allure.attach(
            driver.page_source,
            name=f"DOM страницы ({browser_name})",
            attachment_type=allure.attachment_type.HTML,
        )
    except Exception as exc:
        # Диагностика не должна подменять исходное падение теста, в том числе при сбое Allure.
        logger.warning("Не удалось сохранить состояние браузера: %s", type(exc).__name__)


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: pytest.Item, call: pytest.CallInfo[None]
) -> Generator[None, pytest.TestReport, pytest.TestReport]:
    report = yield
    if not report.failed or report.when not in {"setup", "call"}:
        return report
    if isinstance(item, pytest.Function):
        for browser_name in ("browser", "second_browser"):
            driver = item.funcargs.get(browser_name)
            if isinstance(driver, WebDriver):
                _attach_browser_state(driver, browser_name, item.nodeid)
    return report
