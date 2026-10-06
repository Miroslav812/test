from typing import Any
from uuid import uuid4


def user_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "name": "Automation User",
        "email": f"qa-{uuid4().hex}@example.com",
        "role": "user",
        **overrides,
    }
