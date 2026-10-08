from dataclasses import dataclass


@dataclass(frozen=True)
class UserDraft:
    """Значения формы до сохранения пользователя."""

    name: str
    email: str
    role: str = "user"


@dataclass(frozen=True)
class UserRow:
    id: str
    name: str
    email: str
    role: str
