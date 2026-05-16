from __future__ import annotations

import hashlib
import hmac
import time
from urllib.parse import urlencode


def sign_panel_params(user_id: int, secret: str, ttl_seconds: int = 3600) -> dict[str, str]:
    exp = str(int(time.time()) + ttl_seconds)
    uid = str(user_id)
    payload = f"{uid}:{exp}".encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return {"uid": uid, "exp": exp, "sig": sig}


def build_panel_url(base_url: str, user_id: int, secret: str, ttl_seconds: int = 3600) -> str:
    params = sign_panel_params(user_id, secret, ttl_seconds=ttl_seconds)
    return f"{base_url.rstrip('/')}/panel?{urlencode(params)}"



