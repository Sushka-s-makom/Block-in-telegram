from __future__ import annotations

import html
import logging
import os
from dataclasses import dataclass
from urllib.parse import quote_plus

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse
from telethon import TelegramClient
from telethon.errors import (
    PasswordHashInvalidError,
    PeerIdInvalidError,
    PhoneCodeExpiredError,
    PhoneCodeInvalidError,
    PhoneNumberFloodError,
    PhoneNumberInvalidError,
    SessionPasswordNeededError,
    UserIdInvalidError,
    UsernameInvalidError,
    UsernameNotOccupiedError,
)
from telethon.sessions import StringSession

from app.config import ensure_runtime_dirs, load_base_settings
from app.core.checker import (
    BlockStatusUndeterminedError,
    check_blocked_via_call,
    check_blocked_via_theme,
    check_blocked_with_fallback,
    resolve_user_id,
)
from app.core.panel_links import verify_panel_params
from app.db.storage import delete_session, get_session, init_db, save_session
from app.logging_utils import configure_logging

logger = logging.getLogger(__name__)
app = FastAPI()


@dataclass(slots=True)
class PendingAuth:
    client: TelegramClient
    phone: str
    phone_code_hash: str
    stage: str


PENDING_AUTHS: dict[int, PendingAuth] = {}
SETTINGS = load_base_settings()
configure_logging()
ensure_runtime_dirs()
init_db()


def user_session_path(user_id: int) -> str:
    return os.path.join(SETTINGS.user_session_dir, str(user_id))


def panel_url_query(uid: str, exp: str, sig: str) -> str:
    return f"/panel?uid={uid}&exp={exp}&sig={sig}"


def panel_url_with_message(uid: str, exp: str, sig: str, message: str) -> str:
    return f"{panel_url_query(uid, exp, sig)}&msg={quote_plus(message)}"


def ensure_access(uid: str, exp: str, sig: str) -> int:
    if not verify_panel_params(uid, exp, sig, SETTINGS.app_secret):
        raise HTTPException(status_code=403, detail="Invalid or expired panel link")
    return int(uid)


async def create_user_client(user_id: int) -> TelegramClient:
    stored = get_session(user_id)
    session = StringSession(stored.session_string) if stored is not None else user_session_path(user_id)
    client = TelegramClient(session, SETTINGS.api_id, SETTINGS.api_hash)
    await client.connect()
    return client


async def is_connected(user_id: int) -> bool:
    client = await create_user_client(user_id)
    try:
        return await client.is_user_authorized()
    finally:
        await client.disconnect()


async def cleanup_pending_auth(user_id: int) -> None:
    pending = PENDING_AUTHS.pop(user_id, None)
    if pending is not None:
        await pending.client.disconnect()


def render_page(
    uid: str,
    exp: str,
    sig: str,
    *,
    content: str,
    title: str = "Block Checker",
) -> HTMLResponse:
    return HTMLResponse(
        f"""
<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f4f1ea;
      --card: #fffdf8;
      --text: #1f1a17;
      --muted: #6c625a;
      --accent: #1f6feb;
      --danger: #c0392b;
      --border: #d8cec2;
    }}
    body {{
      margin: 0;
      font-family: ui-sans-serif, -apple-system, BlinkMacSystemFont, sans-serif;
      background:
        radial-gradient(circle at top left, #ffe8c7 0, transparent 24%),
        radial-gradient(circle at bottom right, #dcecff 0, transparent 26%),
        var(--bg);
      color: var(--text);
    }}
    .wrap {{
      max-width: 760px;
      margin: 0 auto;
      padding: 24px 16px 48px;
    }}
    .card {{
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 18px;
      padding: 20px;
      box-shadow: 0 16px 40px rgba(31, 26, 23, 0.08);
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 28px;
    }}
    p {{
      color: var(--muted);
      line-height: 1.5;
    }}
    form {{
      display: grid;
      gap: 12px;
      margin-top: 18px;
    }}
    input, button {{
      font: inherit;
    }}
    input {{
      padding: 12px 14px;
      border-radius: 12px;
      border: 1px solid var(--border);
      background: white;
    }}
    button {{
      display: inline-block;
      padding: 12px 16px;
      border-radius: 12px;
      border: 0;
      background: var(--accent);
      color: white;
      cursor: pointer;
      text-align: center;
    }}
    .button-danger {{
      background: var(--danger);
    }}
    .grid {{
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    }}
    .note {{
      margin-top: 14px;
      padding: 12px 14px;
      border-radius: 12px;
      background: #f7f2eb;
      color: var(--text);
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      {content}
    </div>
  </div>
</body>
</html>
"""
    )


def hidden_inputs(uid: str, exp: str, sig: str) -> str:
    return (
        f'<input type="hidden" name="uid" value="{html.escape(uid)}">'
        f'<input type="hidden" name="exp" value="{html.escape(exp)}">'
        f'<input type="hidden" name="sig" value="{html.escape(sig)}">'
    )


async def render_panel(uid: str, exp: str, sig: str, message: str = "") -> HTMLResponse:
    user_id = ensure_access(uid, exp, sig)
    connected = await is_connected(user_id)
    pending = PENDING_AUTHS.get(user_id)
    message_block = f'<div class="note">{html.escape(message)}</div>' if message else ""

    if pending is not None:
        if pending.stage == "code":
            return render_page(
                uid,
                exp,
                sig,
                content=f"""
<h1>Подтверждение входа</h1>
<p>Введите код, который Telegram отправил на номер <b>{html.escape(pending.phone)}</b>.</p>
{message_block}
<form method="post" action="/auth/code">
  {hidden_inputs(uid, exp, sig)}
  <input name="code" placeholder="Код из Telegram" required>
  <button type="submit">Подтвердить код</button>
</form>
""",
            )

        if pending.stage == "password":
            return render_page(
                uid,
                exp,
                sig,
                content=f"""
<h1>Двухфакторная защита</h1>
<p>Введите пароль двухфакторной защиты для завершения входа.</p>
{message_block}
<form method="post" action="/auth/password">
  {hidden_inputs(uid, exp, sig)}
  <input type="password" name="password" placeholder="Пароль 2FA" required>
  <button type="submit">Подтвердить пароль</button>
</form>
""",
            )

    if not connected:
        return render_page(
            uid,
            exp,
            sig,
            content=f"""
<h1>Подключение аккаунта</h1>
<p>Подключите аккаунт через телефон и код. После входа панель сохранит его как <code>StringSession</code> в базе.</p>
{message_block}
<form method="post" action="/auth/start">
  {hidden_inputs(uid, exp, sig)}
  <input name="phone" placeholder="+79991234567" required>
  <button type="submit">Подключить через телефон и код</button>
</form>
""",
        )

    return render_page(
        uid,
        exp,
        sig,
        content=f"""
<h1>Block Checker</h1>
<p>Аккаунт подключён. Введите <code>@username</code> или numeric ID и выберите режим проверки.</p>
{message_block}
<form method="post" action="/check">
  {hidden_inputs(uid, exp, sig)}
  <input name="target" placeholder="@username или 123456789" required>
  <div class="grid">
    <button type="submit" name="mode" value="theme">Тихая проверка</button>
    <button type="submit" name="mode" value="call">Заметная проверка</button>
    <button type="submit" name="mode" value="combo">Тихая + звонок</button>
  </div>
</form>
<form method="post" action="/logout">
  {hidden_inputs(uid, exp, sig)}
  <button class="button-danger" type="submit">Отключить аккаунт</button>
</form>
""",
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/panel", response_class=HTMLResponse)
async def panel(uid: str, exp: str, sig: str, msg: str = "") -> HTMLResponse:
    return await render_panel(uid, exp, sig, msg)


@app.post("/auth/start")
async def auth_start(
    uid: str = Form(...),
    exp: str = Form(...),
    sig: str = Form(...),
    phone: str = Form(...),
) -> RedirectResponse:
    user_id = ensure_access(uid, exp, sig)
    await cleanup_pending_auth(user_id)
    client = await create_user_client(user_id)

    try:
        result = await client.send_code_request(phone.strip())
    except (PhoneNumberInvalidError, PhoneNumberFloodError):
        await client.disconnect()
        return RedirectResponse(
            url=panel_url_with_message(uid, exp, sig, "Неверный или временно ограниченный номер"),
            status_code=303,
        )

    PENDING_AUTHS[user_id] = PendingAuth(
        client=client,
        phone=phone.strip(),
        phone_code_hash=result.phone_code_hash,
        stage="code",
    )
    return RedirectResponse(url=panel_url_query(uid, exp, sig), status_code=303)


@app.post("/auth/code")
async def auth_code(
    uid: str = Form(...),
    exp: str = Form(...),
    sig: str = Form(...),
    code: str = Form(...),
) -> RedirectResponse:
    user_id = ensure_access(uid, exp, sig)
    pending = PENDING_AUTHS.get(user_id)
    if pending is None or pending.stage != "code":
        return RedirectResponse(url=panel_url_query(uid, exp, sig), status_code=303)

    try:
        await pending.client.sign_in(
            phone=pending.phone,
            code=code.strip(),
            phone_code_hash=pending.phone_code_hash,
        )
    except SessionPasswordNeededError:
        pending.stage = "password"
        return RedirectResponse(url=panel_url_query(uid, exp, sig), status_code=303)
    except PhoneCodeInvalidError:
        return RedirectResponse(
            url=panel_url_with_message(uid, exp, sig, "Неверный код"),
            status_code=303,
        )
    except PhoneCodeExpiredError:
        await cleanup_pending_auth(user_id)
        return RedirectResponse(
            url=panel_url_with_message(uid, exp, sig, "Код истёк. Начните заново"),
            status_code=303,
        )

    me = await pending.client.get_me()
    if me is not None:
        save_session(user_id, me.id, pending.client.session.save())
    await cleanup_pending_auth(user_id)
    return RedirectResponse(
        url=panel_url_with_message(uid, exp, sig, "Аккаунт подключён"),
        status_code=303,
    )


@app.post("/auth/password")
async def auth_password(
    uid: str = Form(...),
    exp: str = Form(...),
    sig: str = Form(...),
    password: str = Form(...),
) -> RedirectResponse:
    user_id = ensure_access(uid, exp, sig)
    pending = PENDING_AUTHS.get(user_id)
    if pending is None or pending.stage != "password":
        return RedirectResponse(url=panel_url_query(uid, exp, sig), status_code=303)

    try:
        await pending.client.sign_in(password=password)
    except PasswordHashInvalidError:
        return RedirectResponse(
            url=panel_url_with_message(uid, exp, sig, "Неверный пароль 2FA"),
            status_code=303,
        )

    me = await pending.client.get_me()
    if me is not None:
        save_session(user_id, me.id, pending.client.session.save())
    await cleanup_pending_auth(user_id)
    return RedirectResponse(
        url=panel_url_with_message(uid, exp, sig, "Аккаунт подключён"),
        status_code=303,
    )


@app.post("/logout")
async def logout(
    uid: str = Form(...),
    exp: str = Form(...),
    sig: str = Form(...),
) -> RedirectResponse:
    user_id = ensure_access(uid, exp, sig)
    await cleanup_pending_auth(user_id)
    delete_session(user_id)
    for suffix in (".session", ".session-journal"):
        session_file = f"{user_session_path(user_id)}{suffix}"
        if os.path.exists(session_file):
            os.remove(session_file)

    return RedirectResponse(
        url=panel_url_with_message(uid, exp, sig, "Аккаунт отключён"),
        status_code=303,
    )


@app.post("/check")
async def check(
    uid: str = Form(...),
    exp: str = Form(...),
    sig: str = Form(...),
    target: str = Form(...),
    mode: str = Form(...),
) -> RedirectResponse:
    user_id = ensure_access(uid, exp, sig)
    client = await create_user_client(user_id)

    try:
        if not await client.is_user_authorized():
            return RedirectResponse(
                url=panel_url_with_message(uid, exp, sig, "Сначала подключите аккаунт"),
                status_code=303,
            )

        target_user_id = await resolve_user_id(client, target.strip())
        if mode == "theme":
            is_blocked = await check_blocked_via_theme(client, target_user_id)
        elif mode == "call":
            is_blocked = await check_blocked_via_call(client, target_user_id)
        else:
            is_blocked = await check_blocked_with_fallback(client, target_user_id)

        result_text = "Пользователь вас заблокировал" if is_blocked else "Пользователь вас не заблокировал"
    except (
        BlockStatusUndeterminedError,
        PeerIdInvalidError,
        UserIdInvalidError,
        UsernameInvalidError,
        UsernameNotOccupiedError,
        TypeError,
        ValueError,
    ):
        logger.exception("web check failed uid=%s target=%r mode=%s", user_id, target, mode)
        result_text = "Не удалось определить статус пользователя"
    finally:
        await client.disconnect()

    return RedirectResponse(
        url=panel_url_with_message(uid, exp, sig, result_text),
        status_code=303,
    )
