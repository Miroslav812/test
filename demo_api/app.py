from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from typing import Annotated, Literal
from uuid import UUID, uuid4

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, EmailStr, Field

DEMO_TOKEN = "local-demo-token"


class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Login(Payload):
    username: str
    password: str


class NewUser(Payload):
    name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    role: Literal["user", "admin"] = "user"


class UserPatch(Payload):
    name: str = Field(min_length=1, max_length=100)


class StoredUser(NewUser):
    id: UUID
    created_at: datetime


def authorize(authorization: Annotated[str | None, Header()] = None) -> None:
    if authorization != f"Bearer {DEMO_TOKEN}":
        raise HTTPException(401, "Unauthorized", headers={"WWW-Authenticate": "Bearer"})


def create_app() -> FastAPI:
    app = FastAPI(title="REST Testkit Demo", version="1.0.0")
    web_directory = Path(__file__).parent / "web"
    app.mount("/ui/assets", StaticFiles(directory=web_directory), name="ui-assets")
    users: dict[UUID, StoredUser] = {}
    lock = RLock()
    auth = [Depends(authorize)]

    @app.get("/ui", include_in_schema=False)
    def ui() -> FileResponse:
        # UI и API имеют общий origin: браузер отправляет реальные запросы без настройки CORS.
        return FileResponse(web_directory / "index.html")

    def find(user_id: UUID) -> StoredUser:
        if user_id not in users:
            raise HTTPException(404, "User not found")
        return users[user_id]

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/auth/token")
    def login(payload: Login) -> dict[str, str]:
        if payload.username != "demo" or payload.password != "demo":
            raise HTTPException(401, "Invalid credentials")
        return {"access_token": DEMO_TOKEN, "token_type": "bearer"}

    @app.post("/users", status_code=201, dependencies=auth)
    def create_user(payload: NewUser, response: Response) -> StoredUser:
        with lock:
            if any(user.email == payload.email for user in users.values()):
                raise HTTPException(409, "Email already exists")
            user = StoredUser(**payload.model_dump(), id=uuid4(), created_at=datetime.now(UTC))
            users[user.id] = user
            response.headers["Location"] = f"/users/{user.id}"
            return user

    @app.get("/users", dependencies=auth)
    def list_users(
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        offset: Annotated[int, Query(ge=0)] = 0,
    ) -> dict[str, object]:
        with lock:
            items = list(users.values())
            return {
                "items": items[offset : offset + limit],
                "total": len(items),
                "limit": limit,
                "offset": offset,
            }

    @app.get("/users/{user_id}", dependencies=auth)
    def get_user(user_id: UUID) -> StoredUser:
        with lock:
            return find(user_id)

    @app.patch("/users/{user_id}", dependencies=auth)
    def update_user(user_id: UUID, payload: UserPatch) -> StoredUser:
        with lock:
            current = find(user_id)
            updated = current.model_copy(update={"name": payload.name})
            users[user_id] = updated
            return updated

    @app.delete("/users/{user_id}", status_code=204, dependencies=auth)
    def delete_user(user_id: UUID) -> Response:
        with lock:
            find(user_id)
            del users[user_id]
            return Response(status_code=204)

    return app
