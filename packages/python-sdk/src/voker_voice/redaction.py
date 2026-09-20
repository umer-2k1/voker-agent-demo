from collections.abc import Mapping
from typing import Any

SECRET_FIELD_NAMES = {
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "password",
    "secret",
    "token",
}


def redact(value: Any, *, max_string_length: int = 10_000) -> Any:
    """Remove common credentials and bound exported content recursively."""

    if isinstance(value, Mapping):
        return {
            str(key): "[REDACTED]"
            if str(key).lower().replace("-", "_") in SECRET_FIELD_NAMES
            else redact(item, max_string_length=max_string_length)
            for key, item in value.items()
        }
    if isinstance(value, list | tuple):
        return [redact(item, max_string_length=max_string_length) for item in value]
    if isinstance(value, str) and len(value) > max_string_length:
        return f"{value[:max_string_length]}…[TRUNCATED]"
    return value
