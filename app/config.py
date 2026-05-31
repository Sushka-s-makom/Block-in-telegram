from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
SESSION_DIR = BASE_DIR / "session"
USER_SESSION_DIR = SESSION_DIR / "users"
DB_PATH = BASE_DIR / "block_checker.db"


@dataclass(slots=True)
class BaseSettings:
    api_id: int
    api_hash: str
    app_secret: str


@dataclass(slots=True)
class BotSettings(BaseSettings):
    bot_token: str
    web_app_url: str
    bot_string_session: str | None = None
    bot_session_name: str = str(SESSION_DIR / "bot")
    user_session_dir: str = str(USER_SESSION_DIR)

def ensure_runtime_dirs() -> None:
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    USER_SESSION_DIR.mkdir(parents=True, exist_ok=True)


def _load_env_values() -> tuple[str | None, str | None, str | None, str | None, str | None]:
    load_dotenv()
    return (
        os.getenv("API_ID"),
        os.getenv("API_HASH"),
        os.getenv("BOT_TOKEN"),
        os.getenv("WEB_APP_URL"),
        os.getenv("APP_SECRET"),
    )


def _parse_api_id(api_id_raw: str) -> int:
    try:
        return int(api_id_raw)
    except ValueError as exc:
        raise RuntimeError("API_ID must be an integer") from exc


def load_base_settings() -> BaseSettings:
    api_id_raw, api_hash, _bot_token, _web_app_url, app_secret = _load_env_values()

    if not api_id_raw:
        raise RuntimeError("Missing API_ID in environment")
    if not api_hash:
        raise RuntimeError("Missing API_HASH in environment")
    if not app_secret:
        raise RuntimeError("Missing APP_SECRET in environment")

    return BaseSettings(
        api_id=_parse_api_id(api_id_raw),
        api_hash=api_hash,
        app_secret=app_secret,
    )


def load_bot_settings() -> BotSettings:
    api_id_raw, api_hash, bot_token, web_app_url, app_secret = _load_env_values()
    bot_string_session = os.getenv("BOT_STRING_SESSION") or None

    if not api_id_raw:
        raise RuntimeError("Missing API_ID in environment")
    if not api_hash:
        raise RuntimeError("Missing API_HASH in environment")
    if not bot_token:
        raise RuntimeError("Missing BOT_TOKEN in environment")
    if not web_app_url:
        raise RuntimeError("Missing WEB_APP_URL in environment")
    if not app_secret:
        raise RuntimeError("Missing APP_SECRET in environment")

    return BotSettings(
        api_id=_parse_api_id(api_id_raw),
        api_hash=api_hash,
        bot_token=bot_token,
        web_app_url=web_app_url,
        app_secret=app_secret,
        bot_string_session=bot_string_session,
    )
