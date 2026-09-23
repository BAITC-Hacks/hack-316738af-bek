"""Optional browser access gate; API credentials never enter the frontend bundle."""

import hashlib
import hmac
import re
import secrets
import time

from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse

ACCESS_COOKIE = "qurylym_access"
ACCESS_TTL = 4 * 60 * 60


def issue_access(secret, now=None):
    expires = int(time.time() if now is None else now) + ACCESS_TTL
    body = f"{expires}.{secrets.token_hex(16)}"
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return f"{body}.{signature}"


def valid_access(value, secret, now=None):
    if not secret or not re.fullmatch(r"\d{10}\.[a-f0-9]{32}\.[a-f0-9]{64}", value):
        return False
    body, signature = value.rsplit(".", 1)
    current = int(time.time() if now is None else now)
    expires = int(body.split(".")[0])
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).hexdigest()
    return current < expires <= current + ACCESS_TTL and hmac.compare_digest(signature, expected)


def has_access(request, settings):
    if not settings.access_token:
        return True
    supplied = request.headers.get("authorization", "")
    return hmac.compare_digest(supplied.encode(), ("Bearer " + settings.access_token).encode()) or valid_access(
        request.cookies.get(ACCESS_COOKIE, ""), settings.access_token
    )


def access_page(message="", status=200):
    # Only fixed application messages are interpolated; submitted values are never echoed.
    page = """<!doctype html><html lang="kk"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Qurylym AI — кіру</title>
<style>body{margin:0;background:#f3f5f9;color:#192233;font:16px system-ui;display:grid;
min-height:100vh;place-items:center}main{box-sizing:border-box;width:min(92vw,440px);padding:36px;
background:white;border:1px solid #dce2eb;border-radius:20px}h1{font-size:30px;margin:0 0 12px}
p{line-height:1.6}label{display:block;margin-top:24px}input,button{box-sizing:border-box;width:100%;
font:inherit;padding:14px;border-radius:9px;margin-top:8px}input{border:1px solid #8090a8}
button{background:#245bd4;color:white;border:0;cursor:pointer}small{display:block;margin-top:20px;
color:#59677c}#error{color:#a82020}</style><main><h1>Qurylym AI</h1>
<p>Ұйымдық өзгерістерді дәлелдермен талдау.</p><p id="error" role="status">MESSAGE</p>
<form method="post" action="/access"><label for="code">Қолжетімділік коды</label>
<input id="code" name="code" type="password" required maxlength="512" autocomplete="current-password">
<button type="submit">Кіру</button></form><small>Кодты жоба командасынан алыңыз.
Бұл өріске OpenAI немесе NVIDIA API кілтін енгізбеңіз.</small></main></html>"""
    return HTMLResponse(
        page.replace("MESSAGE", message),
        status_code=status,
        headers={
            "Cache-Control": "no-store",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        },
    )


def install_access(app, settings):
    attempts = {}

    @app.get("/access", include_in_schema=False)
    async def login_page(request: Request):
        return RedirectResponse("/", status_code=303) if has_access(request, settings) else access_page()

    @app.post("/access", include_in_schema=False)
    async def login(request: Request):
        if not settings.access_token:
            return RedirectResponse("/", status_code=303)
        origin = request.headers.get("origin")
        if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
            return access_page("Кіру сұрауының адресі сәйкес емес.", 400)
        now = time.monotonic()
        for key, (_, started) in list(attempts.items()):
            if now - started >= 60:
                del attempts[key]
        ip = request.client.host if request.client else "unknown"
        count, started = attempts.get(ip, (0, now))
        if count >= 10 or (ip not in attempts and len(attempts) >= 1000):
            return access_page("Бір минуттан кейін қайта көріңіз.", 429)
        attempts[ip] = (count + 1, started)
        async with request.form(max_files=0, max_fields=1, max_part_size=1024) as form:
            code = form.get("code", "")
            if not isinstance(code, str) or len(code) > 512:
                return access_page("Қолжетімділік коды жарамсыз.", 400)
            if not hmac.compare_digest(code.encode(), settings.access_token.encode()):
                return access_page("Қолжетімділік коды дұрыс емес.", 403)
        attempts.pop(ip, None)
        response = RedirectResponse("/", status_code=303)
        response.set_cookie(
            ACCESS_COOKIE,
            issue_access(settings.access_token),
            httponly=True,
            secure=settings.secure_cookie,
            samesite="strict",
            max_age=ACCESS_TTL,
            path="/",
        )
        return response
