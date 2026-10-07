# API & Selenium UI Testkit

Проект автотестирования REST API и UI на **Python + pytest + HTTPX + Selenium**.
API-набор запускается сразу:
демонстрационный FastAPI-сервис поднимается на свободном локальном порту, тесты
выполняют настоящие HTTP-запросы, затем сервис останавливается. Внешние сервисы,
Docker и секреты для первого запуска не нужны.
UI-набор проверяет ту же систему через настоящий Chrome или Edge. Он запускается
отдельно и требует установленный браузер.

## Быстрый старт

### Windows 10/11: запуск через терминал

Если Smart App Control («Интеллектуальное управление приложениями») блокирует
`run-tests.cmd`, это происходит до запуска установки и тестов. Для такого компьютера
используйте встроенный менеджер WinGet и команды ниже. Отключать защиту Windows
или менять системную политику выполнения скриптов не требуется.

1. Откройте PowerShell из меню «Пуск» и установите uv из официального пакета WinGet:

```powershell
winget install --id astral-sh.uv --exact --source winget
```

2. Закройте окно после завершения установки. Откройте уже распакованную папку
   `test-main` в Проводнике; в адресной строке введите `powershell` и нажмите Enter.
   Новое окно откроется в папке проекта и подхватит обновлённый PATH.
3. Выполните по очереди:

```powershell
uv sync --frozen --no-default-groups --group test
uv run --frozen --no-default-groups --group test pytest
```

uv автоматически найдёт или скачает Python 3.12 и подготовит `.venv`. При успешном
прогоне ожидается `39 passed`. Если WinGet отсутствует или Windows блокирует сам
`uv.exe`, сохраните точный текст сообщения для дальнейшей диагностики. Не отключайте
защиту компьютера для продолжения установки.

### Windows 10/11: запуск двойным щелчком, если разрешён политикой компьютера

1. [Скачайте ZIP проекта](https://github.com/Miroslav812/test/archive/refs/heads/main.zip).
2. Распакуйте весь архив в доступную для записи папку, например `Документы`.
3. Откройте распакованную папку `test-main` и дважды нажмите **`run-tests.cmd`**.

Скрипт скачает uv 0.12.19 из официального GitHub release, проверит SHA-256 архива,
затем uv автоматически найдёт или скачает Python 3.12 и установит зависимости
тестов в `.venv`. После установки сразу запустится API-набор (39 проверок). Окно останется
открытым, чтобы можно было прочитать результат; для закрытия нажмите любую клавишу.
Для повторного запуска снова откройте `run-tests.cmd`.

Git, Docker, Java, редактор кода и Allure CLI для этого запуска не требуются.
Не устанавливаются и инструменты разработки Ruff/mypy. Интернет нужен при первой
установке. uv сохраняется в `%LOCALAPPDATA%\RestApiTestkit\tools\uv-0.12.19`;
системный PATH и существующий Python не изменяются. Не требуется запускать файл
от имени администратора. Если корпоративные ограничения запрещают скрипты или
загрузки, сохраните текст ошибки для диагностики.

Результаты: `reports\junit.xml` и `reports\allure-results`. Учебный API запускается
и останавливается автоматически; никакие внешние токены для тестов не нужны.

### Запуск из терминала / настройка для разработки

Требуются Python 3.12 или 3.13 и [uv](https://docs.astral.sh/uv/getting-started/installation/).
Проверенная версия uv: `0.12.19`. Все команды выполняются из корня репозитория.

```bash
uv sync --frozen
uv run --frozen pytest
```

`uv.lock` фиксирует версии прямых и транзитивных зависимостей. `.venv` создаётся
автоматически. Linux/macOS могут использовать команды Makefile; сами команды uv
работают и на Windows.

Только зависимости тестов, без Ruff/mypy:

```bash
uv sync --frozen --no-default-groups --group test
uv run --frozen --no-default-groups --group test pytest
```

## Возможности

- CRUD пользователей с проверкой сохранённых значений, а не только HTTP-статуса.
- Bearer-авторизация, неверные credentials, запросы без токена и с неверным токеном.
- Валидация обязательных полей, email, ролей и границ пагинации; ошибки 401/404/409/422.
- Строгие Pydantic-контракты: типы, UUID, даты, обязательные и лишние поля.
- Фабрики уникальных данных и teardown, удаляющий созданные записи даже при падении теста.
- Изоляция хранилища и HTTP-порта для каждого pytest-xdist worker.
- Таймауты запросов, проверка TLS по умолчанию, запрет автоматических редиректов.
- Метаданные запросов в собственном логе клиента без токенов, query и тел запросов.
- Allure-шаги, JUnit XML, Ruff, mypy и GitHub Actions.
- Selenium Page Objects, стабильные `data-testid` и явные ожидания без `sleep` в UI-тестах.
- UI: вход/выход, формы, роли, создание/изменение/удаление пользователей и поиск.
- Проверка сохранения UI-действий через API и безопасного отображения пользовательского HTML.
- Новый браузер для каждого теста; screenshot и DOM в Allure при падении.

## UI-тесты Selenium: Windows 10/11

Откройте PowerShell **в папке проекта с `pyproject.toml`**. Установленный Edge можно
использовать сразу; если выбран Chrome, предварительно установите Google Chrome.

```powershell
uv sync --frozen --no-default-groups --group ui
uv run --frozen --no-default-groups --group ui pytest tests/ui --browser edge --headed
```

`--headed` показывает окно браузера. Без него тесты выполняются headless.
Для Chrome замените `--browser edge` на `--browser chrome`. Chrome — выбор по умолчанию.
Локальная страница и API поднимаются и останавливаются фикстурами; отдельно запускать
сервер не нужно. Ожидается **12 UI-тестов**.

Selenium Manager автоматически подбирает WebDriver под установленный браузер при
первом запуске; для загрузки нужен Интернет. Если менеджер не может скачать драйвер,
используйте официальный совместимый драйвер через `--driver-path` / `UI_DRIVER_PATH`.
Не отключайте TLS или Smart App Control ради загрузки. Подробности: [docs/ui-testing.md](docs/ui-testing.md).

Отчёты с UI-артефактами:

```powershell
uv run --frozen --no-default-groups --group ui pytest tests/ui --browser edge --alluredir=reports/ui/allure-results --clean-alluredir --junitxml=reports/ui/junit.xml
```

Для **всех 51 теста (API + инфраструктура + UI)**:

```powershell
uv run --frozen --no-default-groups --group ui pytest tests --browser edge
```

Команда `pytest` без указания папки по-прежнему выполняет 39 API/инфраструктурных
проверок. Это сохраняет минимальный запуск без установки браузера и Selenium.

## Структура

```text
src/restkit/
  config.py           # окружение, .env, таймауты, SecretStr
  client.py           # HTTP-транспорт и пул соединений
  contracts.py        # схемы ответов и общие assertions
  apis/users.py       # методы конкретного ресурса
  ui/pages.py         # BasePage, LoginPage, UsersPage
demo_api/app.py        # учебный REST API с изолированным in-memory хранилищем
demo_api/web/          # интерфейс, работающий с тем же REST API
tests/
  conftest.py          # запуск сервера, клиенты, авторизация, cleanup
  factories.py        # уникальные данные
  api/                # функциональные REST-сценарии
  unit/               # проверки инфраструктуры клиента
  ui/                 # Selenium-фикстуры, браузерные сценарии и диагностика
.github/workflows/     # проверки и отчёты в CI
docs/                 # контракт API и правила расширения
```

## Запуск проверок

```bash
make check             # lint, формат и строгая проверка типов
make test              # API + инфраструктура, Allure results и JUnit XML
make smoke             # критические сценарии
make parallel          # API + инфраструктура в двух workers
make ui                # UI, headless Chrome
make ui-headed         # UI с видимым окном Chrome
make all               # все API + UI тесты
# Без make:
uv run --frozen pytest -m negative
uv run --frozen pytest -m contract
uv run --frozen pytest -n 2
```

Проверки типов/линтер, API и UI-наборы обязательны для CI. Отдельный smoke-набор
предназначен для быстрой обратной связи. Автоматических перезапусков упавших тестов нет.

## Отчёты

```bash
uv run --frozen pytest --alluredir=reports/allure-results --clean-alluredir --junitxml=reports/junit.xml
```

Результаты сохраняются в `reports/` и не коммитятся. Для HTML-отчёта отдельно
установите [Allure CLI](https://allurereport.org/docs/install/) и выполните `make report`.
Allure CLI не требуется для тестов или получения JSON-результатов. CI сохраняет
результаты как artifacts для каждой версии Python и браузера на 14 дней.
Отдельная UI-матрица выполняется на Windows в Chrome и Edge.

Для внешних стендов отчёты и traceback могут содержать тестовые данные. Не включайте
HTTPX DEBUG/INFO, `--showlocals` или вложения сырых headers/body при работе с секретами.

## Подключение другого API

Любой адрес можно задать через `API_BASE_URL`, но тесты должны соответствовать
эндпоинтам и контракту конкретного сервиса. Текущий пример ожидает [контракт Users](docs/api-contract.md).
Для другого API адаптируйте `apis/`, `contracts.py`, фабрики и сценарии.

1. Используйте выделенный тестовый стенд с согласованными тестовыми данными.
2. Скопируйте `.env.example` в `.env`, задайте `API_BASE_URL` и `API_TOKEN`.
   `.env` игнорируется Git. В CI используйте Secrets, а в облачной среде — защищённые настройки.
3. Запустите проверки чтения. Demo-only тесты авторизации и изменяющие данные
   сценарии будут явно **skipped**, а не counted as passed:

```bash
uv run --frozen pytest tests/api --api-mode external
```

4. Для полного набора на стенде с совместимым контрактом разрешите изменение данных:

```bash
uv run --frozen pytest tests/api --api-mode external --allow-mutations
```

Можно переопределить адрес: `--base-url https://your-test-api.example/v1`.
Внешний режим не запускает локальный сервис. В demo-режиме URL и токен из `.env`
не используются. `API_TIMEOUT_SECONDS` задаёт таймаут (по умолчанию 10 секунд).

## Демонстрационный сервис отдельно

```bash
make demo
```

Порт 8000. OpenAPI доступен по маршруту `/openapi.json`, Swagger — `/docs`.
Учебный login: `demo` / `demo`. Хранилище сбрасывается при остановке процесса.
Это демонстрационный сервис: он не предназначен для продакшена.

Правила добавления ресурсов и тестов: [docs/extending.md](docs/extending.md).
