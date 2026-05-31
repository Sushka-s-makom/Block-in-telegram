from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

from dotenv import load_dotenv
from telethon.sessions import StringSession
from telethon.sync import TelegramClient


def load_settings() -> tuple[int, str, str | None]:
    load_dotenv()

    api_id_raw = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    proxy_url = os.getenv("PROXY_URL") or None

    if not api_id_raw or not api_hash:
        print("Ошибка: API_ID и API_HASH должны быть указаны в .env")
        print("Получить их можно на https://my.telegram.org")
        raise SystemExit(1)

    try:
        api_id = int(api_id_raw)
    except ValueError as exc:
        raise SystemExit("Ошибка: API_ID должен быть числом") from exc

    return api_id, api_hash, proxy_url




if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
