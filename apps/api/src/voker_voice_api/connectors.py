"""Provider webhook normalization into the canonical Voker Voice envelope."""

import hashlib
from datetime import UTC, datetime
from typing import Any


def provider_event_id(provider: str, delivery_id: str, index: int = 0) -> str:
    digest = hashlib.sha256(f"{provider}:{delivery_id}:{index}".encode()).hexdigest()[:40]
    return f"{provider}_{digest}"


def normalize_vapi(payload: dict[str, Any], delivery_id: str) -> list[dict[str, Any]]:
    message = payload.get("message", payload)
    call = message.get("call", {}) if isinstance(message, dict) else {}
    call_id = str(call.get("id") or message.get("callId") or delivery_id)
    created_at = message.get("timestamp") or datetime.now(UTC).isoformat()
    event_type = str(message.get("type") or "call.status")
    status = "error" if "error" in event_type.lower() else "ok"
    event: dict[str, Any] = {
        "event_id": provider_event_id("vapi", delivery_id),
        "event_type": f"vapi.{event_type}",
        "occurred_at": created_at,
        "external_session_id": call_id,
        "trace_id": hashlib.sha256(call_id.encode()).hexdigest()[:32],
        "source": {"integration": "vapi", "provider": "vapi"},
        "status": status,
        "attributes": {"provider_delivery_id": delivery_id, "provider_event": message},
    }
    if status == "error":
        event["error"] = {"type": "VapiWebhookError", "message": str(message), "retryable": False}
    return [event]


def normalize_retell(payload: dict[str, Any], delivery_id: str) -> list[dict[str, Any]]:
    call = payload.get("call", payload)
    call_id = str(call.get("call_id") or call.get("callId") or delivery_id)
    event_name = str(payload.get("event") or payload.get("event_type") or "call.status")
    status = "error" if "error" in event_name.lower() else "ok"
    event: dict[str, Any] = {
        "event_id": provider_event_id("retell", delivery_id),
        "event_type": f"retell.{event_name}",
        "occurred_at": payload.get("timestamp") or datetime.now(UTC).isoformat(),
        "external_session_id": call_id,
        "trace_id": hashlib.sha256(call_id.encode()).hexdigest()[:32],
        "source": {"integration": "retell", "provider": "retell"},
        "status": status,
        "attributes": {"provider_delivery_id": delivery_id, "provider_event": payload},
    }
    if status == "error":
        event["error"] = {"type": "RetellWebhookError", "message": str(payload), "retryable": False}
    return [event]
