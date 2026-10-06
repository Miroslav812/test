# Контракт демонстрационного API

Базовый путь `/`. JSON-запросы и ответы; даты в ISO 8601 с часовым поясом UTC.
Все `/users` требуют `Authorization: Bearer <token>`.

| Метод | Путь | Успех | Основные ошибки |
| --- | --- | --- | --- |
| GET | `/health` | 200 `{"status":"ok"}` | — |
| POST | `/auth/token` | 200 `access_token`, `token_type` | 401 credentials, 422 payload |
| POST | `/users` | 201 User, header `Location` | 409 duplicate email, 422 payload |
| GET | `/users?limit=20&offset=0` | 200 UserPage | 422 pagination |
| GET | `/users/{uuid}` | 200 User | 404 missing, 422 invalid UUID |
| PATCH | `/users/{uuid}` | 200 User | 404 missing, 422 payload |
| DELETE | `/users/{uuid}` | 204, пустое тело | 404 missing, 422 invalid UUID |

Неавторизованные запросы возвращают 401 и `WWW-Authenticate: Bearer`.

## Входные данные

Login: `{"username":"demo","password":"demo"}`. Возвращаемый токен учебный и
не является секретом реальной системы.

Create: `{"name":"Automation User","email":"unique@example.com","role":"user"}`.
`name` после удаления крайних пробелов: 1–100 символов. Email валидируется.
Роль `user` или `admin`, по умолчанию `user`. Неизвестные поля запрещены.
Email уникален в пределах текущего хранилища.

Patch: `{"name":"New name"}`. Изменяется только имя; правила длины те же.

Pagination: `limit` 1–100; `offset` ≥ 0. Порядок — порядок создания.

## Ответы

User: `id` (UUID), `name` (string), `email` (email), `role` (`user`/`admin`),
`created_at` (ISO 8601).

UserPage: `items` (User[]), `total` (≥ 0), `limit`, `offset`.
`total` — число всех записей, включая те, которые не попали на страницу.

401/404/409: `{"detail":"описание"}`. 422: стандартный FastAPI JSON с массивом
ошибок в `detail`. Полная актуальная OpenAPI-схема формируется из `demo_api/app.py`.
