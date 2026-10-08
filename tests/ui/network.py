from collections.abc import Iterator
from contextlib import contextmanager

from selenium.webdriver.remote.webdriver import WebDriver


@contextmanager
def offline_browser(browser: WebDriver) -> Iterator[None]:
    """Отключаем сеть только браузеру; API-клиент и очистка данных продолжают работать."""
    conditions = {"offline": True, "latency": 0, "downloadThroughput": -1, "uploadThroughput": -1}
    browser.execute_cdp_cmd("Network.enable", {})
    try:
        browser.execute_cdp_cmd("Network.emulateNetworkConditions", conditions)
        yield
    finally:
        # Восстанавливаем сеть и при падении проверки, чтобы не сломать дальнейшую диагностику.
        browser.execute_cdp_cmd(
            "Network.emulateNetworkConditions", {**conditions, "offline": False}
        )
