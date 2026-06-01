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


def build_proxy(proxy_url: str | None) -> object | None:
    if not proxy_url:
        return None

    try:
        import socks
    except ImportError:
        print("Для использования PROXY_URL установите PySocks: .venv/bin/pip install PySocks")
        raise SystemExit(1)

    parsed = urlparse(proxy_url)
    if not parsed.hostname or not parsed.port or not parsed.scheme:
        print("Ошибка: PROXY_URL имеет неверный формат")
        raise SystemExit(1)

    proxy_type = {
        "socks5": socks.SOCKS5,
        "socks4": socks.SOCKS4,
        "http": socks.HTTP,
    }.get(parsed.scheme.lower())

    if proxy_type is None:
        print("Ошибка: поддерживаются только socks5://, socks4:// и http:// прокси")
        raise SystemExit(1)

    return {
        "proxy_type": proxy_type,
        "addr": parsed.hostname,
        "port": parsed.port,
        "username": parsed.username or None,
        "password": parsed.password or None,
        "rdns": True,
    }


def main() -> None:
    api_id, api_hash, proxy_url = load_settings()
    proxy = build_proxy(proxy_url)

    print("=" * 60)
    print("  Генератор user StringSession")
    print("=" * 60)
    print()
    print("API_ID/API_HASH взяты из .env.")
    if proxy_url:
        print(f"Используется прокси: {proxy_url}")
    print()
    print("Подключаюсь к Telegram...")
    print()

    with TelegramClient(StringSession(), api_id, api_hash, proxy=proxy) as client:
        client.start()
        me = client.get_me()

        if me is None:
            print("Ошибка: не удалось получить данные аккаунта")
            raise SystemExit(1)

        if getattr(me, "bot", False):
            print("Ошибка: это bot session, а не user session.")
            print("Нужно вводить номер телефона, а не токен от BotFather.")
            raise SystemExit(1)

        session_string = client.session.save()

    print()
    print("=" * 60)
    print("  Готово! Твой SESSION_STRING:")
    print("=" * 60)
    print()
    print(session_string)
    print()
    print("=" * 60)
    print()
    print("Дальше можно:")
    print("1. Вставить строку в бота командой /session")
    print("2. Или сохранить её в своей инфраструктуре")
    print()
    print(f"SESSION_STRING={session_string}")
    print()
    phone = f"+{me.phone}" if getattr(me, "phone", None) else "unknown"
    full_name = " ".join(part for part in [me.first_name, me.last_name] if part).strip() or "unknown"
    print(f"Аккаунт: {full_name} | {phone}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
