from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services.auth import verify_token


def _user_id_from_header(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    uid = verify_token(auth[7:])
    return f"user:{uid}" if uid is not None else None


def user_or_ip_key(request: Request) -> str:
    return _user_id_from_header(request) or f"ip:{get_remote_address(request)}"


limiter = Limiter(key_func=user_or_ip_key, headers_enabled=True)
