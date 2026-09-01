"""Cookie management — single-account model."""
import json
import time
from pathlib import Path
from typing import Any
from src.config import COOKIES_FILE


def load_cookies(path: Path = COOKIES_FILE) -> list[dict[str, Any]]:
    if path.exists():
        return json.loads(path.read_text())
    return []


def save_cookies(cookies: list[dict[str, Any]], path: Path = COOKIES_FILE):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cookies, indent=2, ensure_ascii=False))


def cookies_to_string(cookies: list[dict[str, Any]]) -> str:
    return "; ".join(
        f'{c["name"]}={c["value"]}' for c in cookies
        if "repeatermock" in c.get("domain", "")
    )


def get_cookie_value(cookies: list[dict[str, Any]], name: str) -> str | None:
    for c in cookies:
        if c["name"] == name:
            return c["value"]
    return None
