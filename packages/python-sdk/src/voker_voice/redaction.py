from collections.abc import Callable, Mapping
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


RedactionHook = Callable[[Any], Any]


def redact(
    value: Any,
    *,
    max_string_length: int = 10_000,
    max_collection_items: int = 100,
    max_depth: int = 12,
    _depth: int = 0,
) -> Any:
    """Remove common credentials and bound exported content recursively."""

    if _depth >= max_depth:
        return "[TRUNCATED:MAX_DEPTH]"
    if isinstance(value, Mapping):
        items = list(value.items())
        mapped_result = {
            str(key): "[REDACTED]"
            if str(key).lower().replace("-", "_") in SECRET_FIELD_NAMES
            else redact(
                item,
                max_string_length=max_string_length,
                max_collection_items=max_collection_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )
            for key, item in items[:max_collection_items]
        }
        if len(items) > max_collection_items:
            mapped_result["[TRUNCATED_ITEMS]"] = len(items) - max_collection_items
        return mapped_result
    if isinstance(value, list | tuple):
        sequence_result = [
            redact(
                item,
                max_string_length=max_string_length,
                max_collection_items=max_collection_items,
                max_depth=max_depth,
                _depth=_depth + 1,
            )
            for item in value[:max_collection_items]
        ]
        if len(value) > max_collection_items:
            sequence_result.append(f"[TRUNCATED_ITEMS:{len(value) - max_collection_items}]")
        return sequence_result
    if isinstance(value, str) and len(value) > max_string_length:
        return f"{value[:max_string_length]}…[TRUNCATED]"
    return value
