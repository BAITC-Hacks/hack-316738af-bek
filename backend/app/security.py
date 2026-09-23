"""Session ownership, request-size limits and browser security headers."""

import hashlib
import re
from urllib.parse import urlsplit

from starlette.responses import JSONResponse

from .access import has_access
from .errors import APIError

COOKIE = "qurylym_session"


def owner_for(request, settings, *, create=False):
    if not has_access(request, settings):
        raise APIError(404, "access_denied", "Қолжетімділік кілті қажет.")
    origin = request.headers.get("origin")
    if origin and request.method not in ("GET", "HEAD", "OPTIONS"):
        actual = urlsplit(str(request.base_url))
        own = f"{actual.scheme}://{actual.netloc}"
        if origin != own and origin not in settings.allowed_origins:
            raise APIError(400, "origin_rejected", "Бұл origin үшін өзгертуге рұқсат жоқ.")
    token = request.cookies.get(COOKIE, "")
    if not re.fullmatch(r"[a-f0-9]{64}", token):
        if not create:
            raise APIError(404, "not_found", "Сессия табылмады. Жаңа талдау ашыңыз.")
        import secrets

        token = secrets.token_hex(32)
    return hashlib.sha256(token.encode()).hexdigest(), token


class BodyTooLarge(Exception):
    pass


class SafetyMiddleware:
    def __init__(self, app, max_file_bytes):
        self.app, self.max_file_bytes = app, max_file_bytes

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        upload = scope["method"] == "POST" and scope["path"].endswith("/documents")
        limit = self.max_file_bytes + 64 * 1024 if upload else 128 * 1024

        async def reject(code, message):
            await JSONResponse({"code": code, "message": message, "retryable": False}, status_code=400)(
                scope, receive, secure_send
            )

        async def secure_send(message):
            if message["type"] == "http.response.start":
                message["headers"] = list(message["headers"]) + [
                    (b"x-content-type-options", b"nosniff"),
                    (b"referrer-policy", b"same-origin" if scope["path"] == "/access" else b"no-referrer"),
                    (b"x-frame-options", b"DENY"),
                    (b"cache-control", b"no-store"),
                ]
                if scope["path"].endswith("/export"):
                    message["headers"].append(
                        (
                            b"content-security-policy",
                            b"default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'",
                        )
                    )
            await send(message)

        try:
            length = int(headers.get(b"content-length", b"0"))
            if length < 0:
                raise ValueError
        except ValueError:
            return await reject("invalid_content_length", "Content-Length жарамсыз.")
        if length > limit:
            return await reject("upload_too_large", "Сұрау/файл рұқсат етілген көлемнен асады.")
        received = 0

        async def bounded_receive():
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooLarge
            return message

        try:
            await self.app(scope, bounded_receive, secure_send)
        except BodyTooLarge:
            await reject("upload_too_large", "Сұрау/файл рұқсат етілген көлемнен асады.")
