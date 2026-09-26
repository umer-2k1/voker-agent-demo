"""Controlled intent vocabulary used by ingestion and post-call analysis."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedIntent:
    value: str
    raw: str


INTENT_LABELS = {
    "appointment_reschedule": "Reschedule appointment",
    "appointment_booking": "Book appointment",
    "appointment_cancellation": "Cancel appointment",
    "billing_refund": "Billing or refund",
    "technical_support": "Technical support",
    "unknown": "Unknown intent",
}


def normalize_intent(value: str) -> NormalizedIntent:
    """Map provider/semantic text into a stable, chart-safe intent taxonomy."""

    raw = value.strip()
    normalized = raw.lower().replace("_", " ").replace("-", " ")
    if any(word in normalized for word in ("reschedul", "move appointment", "change appointment")):
        intent = "appointment_reschedule"
    elif any(word in normalized for word in ("cancel appointment", "appointment cancellation")):
        intent = "appointment_cancellation"
    elif any(word in normalized for word in ("book appointment", "schedule appointment", "new appointment")):
        intent = "appointment_booking"
    elif any(word in normalized for word in ("billing", "invoice", "refund", "charge", "payment")):
        intent = "billing_refund"
    elif any(word in normalized for word in ("technical", "support", "login", "access", "outage")):
        intent = "technical_support"
    else:
        intent = "unknown"
    return NormalizedIntent(value=intent, raw=raw)
