"""Managed provider clients and canonical webhook normalization."""

from __future__ import annotations

import hashlib
import hmac
import re
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import httpx

Provider = Literal["vapi", "retell"]
PROVIDER_BASE_URLS: dict[Provider, str] = {
    "vapi": "https://api.vapi.ai",
    "retell": "https://api.retellai.com",
}


class ConnectorError(RuntimeError):
    """A provider rejected or returned an invalid connector request."""


def provider_event_id(provider: str, stable_key: str, index: int = 0) -> str:
    digest = hashlib.sha256(f"{provider}:{stable_key}:{index}".encode()).hexdigest()[:40]
    return f"{provider}_{digest}"


def _provider_request(
    method: str,
    url: str,
    *,
    api_key: str,
    client: httpx.Client | None = None,
    json_body: dict[str, Any] | None = None,
) -> Any:
    owned = client is None
    transport = client or httpx.Client(timeout=10.0)
    try:
        response = transport.request(
            method,
            url,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=json_body,
        )
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise ConnectorError(f"Provider request failed: {error}") from error
    finally:
        if owned:
            transport.close()


def list_provider_resources(
    provider: Provider, api_key: str, *, client: httpx.Client | None = None
) -> list[dict[str, Any]]:
    """Validate a provider key by listing selectable assistants/agents."""

    if provider == "vapi":
        payload = _provider_request(
            "GET", f"{PROVIDER_BASE_URLS[provider]}/assistant", api_key=api_key, client=client
        )
        raw_items = payload if isinstance(payload, list) else []
    else:
        payload = _provider_request(
            "POST",
            f"{PROVIDER_BASE_URLS[provider]}/v2/list-agents",
            api_key=api_key,
            client=client,
            json_body={"limit": 100},
        )
        raw_items = payload.get("items", []) if isinstance(payload, dict) else []

    resources: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        external_id = item.get("id") if provider == "vapi" else item.get("agent_id")
        if not isinstance(external_id, str) or not external_id:
            continue
        name = item.get("name") or item.get("agent_name") or external_id
        previous_url: str | None = None
        if provider == "vapi" and isinstance(item.get("server"), dict):
            candidate = item["server"].get("url")
            previous_url = candidate if isinstance(candidate, str) else None
        if provider == "retell":
            candidate = item.get("webhook_url")
            previous_url = candidate if isinstance(candidate, str) else None
        resources.append(
            {
                "id": external_id,
                "name": str(name),
                "version": str(item.get("version")) if item.get("version") is not None else None,
                "existing_webhook_url": previous_url,
            }
        )
    return resources


def configure_provider_resources(
    provider: Provider,
    api_key: str,
    resources: list[dict[str, Any]],
    selected_ids: list[str],
    *,
    webhook_url: str,
    webhook_token: str,
    client: httpx.Client | None = None,
) -> list[str]:
    """Point selected provider resources at Voker and return displaced destinations."""

    by_id = {str(item.get("id")): item for item in resources}
    unknown = [item for item in selected_ids if item not in by_id]
    if unknown:
        raise ConnectorError(f"Unknown provider resource: {unknown[0]}")
    forwarding_urls: list[str] = []
    for external_id in selected_ids:
        resource = by_id[external_id]
        old_url = resource.get("existing_webhook_url")
        if isinstance(old_url, str) and old_url and old_url != webhook_url:
            forwarding_urls.append(old_url)
        if provider == "vapi":
            body = {
                "server": {
                    "url": webhook_url,
                    "headers": {"X-Voker-Webhook-Token": webhook_token},
                },
                "serverMessages": [
                    "status-update",
                    "transcript",
                    "tool-calls",
                    "end-of-call-report",
                ],
            }
            url = f"{PROVIDER_BASE_URLS[provider]}/assistant/{external_id}"
        else:
            body = {"webhook_url": webhook_url}
            url = f"{PROVIDER_BASE_URLS[provider]}/update-agent/{external_id}"
        _provider_request("PATCH", url, api_key=api_key, client=client, json_body=body)
    return list(dict.fromkeys(forwarding_urls))


def verify_retell_signature(
    raw_body: bytes,
    api_key: str,
    signature: str | None,
    *,
    now: datetime | None = None,
) -> bool:
    """Verify Retell's timestamped HMAC-SHA256 signature over the raw body."""

    if not signature:
        return False
    match = re.fullmatch(r"v=(\d+),d=([0-9a-fA-F]+)", signature.strip())
    if match is None:
        return False
    timestamp, supplied = match.groups()
    current_ms = int((now or datetime.now(UTC)).timestamp() * 1000)
    if abs(current_ms - int(timestamp)) > int(timedelta(minutes=5).total_seconds() * 1000):
        return False
    expected = hmac.new(api_key.encode(), raw_body + timestamp.encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, supplied.lower())


def _timestamp(value: Any, fallback: Any = None) -> str:
    candidate = value if value is not None else fallback
    if isinstance(candidate, (int, float)):
        seconds = candidate / 1000 if candidate > 10_000_000_000 else candidate
        return datetime.fromtimestamp(seconds, tz=UTC).isoformat()
    if isinstance(candidate, str) and candidate:
        return candidate
    return datetime.now(UTC).isoformat()


def _trace_id(provider: str, call_id: str) -> str:
    return hashlib.sha256(f"{provider}:{call_id}".encode()).hexdigest()[:32]


def _identity(config: dict[str, Any] | None, external_id: Any, fallback: str) -> dict[str, Any]:
    mapping = (config or {}).get("agent_mappings", {})
    mapped = mapping.get(str(external_id), {}) if isinstance(mapping, dict) else {}
    return {
        "id": str(external_id) if external_id else None,
        "name": mapped.get("name") if isinstance(mapped, dict) else fallback,
        "version": mapped.get("version") if isinstance(mapped, dict) else None,
    }


def _base_event(
    provider: str,
    call_id: str,
    stable_key: str,
    event_type: str,
    occurred_at: Any,
    *,
    agent: dict[str, Any],
    status: str = "ok",
    attributes: dict[str, Any] | None = None,
    index: int = 0,
) -> dict[str, Any]:
    return {
        "event_id": provider_event_id(provider, f"{call_id}:{stable_key}", index),
        "event_type": event_type,
        "occurred_at": _timestamp(occurred_at),
        "external_session_id": call_id,
        "trace_id": _trace_id(provider, call_id),
        "agent": agent,
        "source": {"integration": provider, "provider": provider},
        "status": status,
        "attributes": attributes or {},
    }


def _transcript_events(
    provider: str,
    call_id: str,
    messages: Any,
    *,
    agent: dict[str, Any],
    started_at: Any,
) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    events: list[dict[str, Any]] = []
    for index, item in enumerate(messages):
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or item.get("speaker") or "unknown").lower()
        speaker = "agent" if role in {"assistant", "agent"} else "user" if role == "user" else role
        text = item.get("message") or item.get("content") or item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        when = item.get("timestamp") or item.get("start_timestamp") or started_at
        event_type = (
            "agent.transcript.completed" if speaker == "agent" else "user.transcript.completed"
        )
        event = _base_event(
            provider,
            call_id,
            f"transcript:{index}:{hashlib.sha1(text.encode()).hexdigest()[:12]}",
            event_type,
            when,
            agent=agent,
            attributes={"speaker": speaker, "transcript": text},
            index=index,
        )
        event["turn_id"] = f"{provider}-turn-{index}"
        event["sequence"] = index
        event["output" if speaker == "agent" else "input"] = {"text": text}
        events.append(event)
    return events


def _tool_events(
    provider: str,
    call_id: str,
    messages: Any,
    *,
    agent: dict[str, Any],
    occurred_at: Any,
) -> list[dict[str, Any]]:
    if not isinstance(messages, list):
        return []
    events: list[dict[str, Any]] = []
    tool_index = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        calls = message.get("toolCallList") or message.get("tool_calls")
        if not isinstance(calls, list):
            continue
        for call in calls:
            if not isinstance(call, dict):
                continue
            tool_id = str(call.get("id") or f"tool-{tool_index}")
            error_value = call.get("error")
            status = "error" if error_value else "ok"
            event = _base_event(
                provider,
                call_id,
                f"tool:{tool_id}",
                "tool.completed" if not error_value else "tool.error",
                message.get("timestamp") or occurred_at,
                agent=agent,
                status=status,
                attributes={"name": str(call.get("name") or "tool")},
                index=tool_index,
            )
            event["span_id"] = f"{provider}-{tool_id}"[:64]
            arguments = call.get("arguments") or call.get("args")
            result = call.get("result") or call.get("output")
            if isinstance(arguments, dict):
                event["input"] = arguments
            if isinstance(result, dict):
                event["output"] = result
            elif result is not None:
                event["output"] = {"value": str(result)}
            if error_value:
                event["error"] = {
                    "type": f"{provider.title()}ToolError",
                    "message": str(error_value),
                    "retryable": False,
                }
            events.append(event)
            tool_index += 1
    return events


def normalize_vapi(
    payload: dict[str, Any], delivery_id: str, config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Convert Vapi status, transcript, tool, and end-report payloads to canonical events."""

    message = payload.get("message", payload)
    if not isinstance(message, dict):
        return []
    call = message.get("call") if isinstance(message.get("call"), dict) else {}
    call_id = str(call.get("id") or message.get("callId") or delivery_id)
    event_name = str(message.get("type") or "status-update")
    assistant_id = call.get("assistantId") or message.get("assistantId")
    agent = _identity(config, assistant_id, str(call.get("name") or "Vapi assistant"))
    started_at = call.get("startedAt") or call.get("createdAt") or message.get("timestamp")
    ended_at = call.get("endedAt") or message.get("timestamp")
    events: list[dict[str, Any]] = []

    call_status = str(message.get("status") or call.get("status") or "").lower()
    if (event_name == "status-update" and call_status in {"in-progress", "active", "ringing"}) or (
        (event_name == "end-of-call-report" or call_status == "ended") and started_at is not None
    ):
        events.append(
            _base_event(
                "vapi",
                call_id,
                "session-started",
                "session.started",
                started_at,
                agent=agent,
                attributes={"provider_status": call_status, "provider_delivery_id": delivery_id},
            )
        )

    artifact = message.get("artifact") if isinstance(message.get("artifact"), dict) else {}
    messages = artifact.get("messages") or message.get("messages")
    if event_name in {"transcript", "conversation-update", "end-of-call-report"}:
        if event_name == "transcript" and not messages:
            messages = [message]
        events.extend(
            _transcript_events("vapi", call_id, messages, agent=agent, started_at=started_at)
        )
    if event_name in {"tool-calls", "function-call", "end-of-call-report"}:
        events.extend(
            _tool_events("vapi", call_id, messages or [message], agent=agent, occurred_at=ended_at)
        )

    if event_name == "end-of-call-report" or (
        event_name == "status-update" and call_status == "ended"
    ):
        ended_reason = call.get("endedReason") or message.get("endedReason")
        failed = isinstance(ended_reason, str) and any(
            word in ended_reason.lower() for word in ("error", "failed", "timeout")
        )
        analysis = call.get("analysis") if isinstance(call.get("analysis"), dict) else {}
        successful = analysis.get("successEvaluation")
        outcome = "resolved" if successful is True else "failed" if successful is False else None
        attributes: dict[str, Any] = {
            "provider_status": "ended",
            "provider_delivery_id": delivery_id,
            "ended_reason": ended_reason,
        }
        if outcome:
            attributes.update({"outcome": outcome, "outcome_source": "provider"})
        terminal = _base_event(
            "vapi",
            call_id,
            f"session-ended:{event_name}",
            "session.error" if failed else "session.ended",
            ended_at,
            agent=agent,
            status="error" if failed else "ok",
            attributes=attributes,
        )
        if failed:
            terminal["error"] = {
                "type": "VapiCallError",
                "message": str(ended_reason or "Vapi call failed"),
                "retryable": False,
            }
        events.append(terminal)

        cost = call.get("cost") or message.get("cost")
        usage = call.get("usage") if isinstance(call.get("usage"), dict) else {}
        usage_event = _base_event("vapi", call_id, "usage", "usage.recorded", ended_at, agent=agent)
        usage_event["usage"] = {
            "provider": "vapi",
            "model": usage.get("model"),
            "input_tokens": usage.get("promptTokens") or usage.get("input_tokens"),
            "output_tokens": usage.get("completionTokens") or usage.get("output_tokens"),
            "total_tokens": usage.get("totalTokens") or usage.get("total_tokens"),
        }
        if isinstance(cost, (int, float)):
            usage_event["attributes"] = {"provider_cost_micros": round(cost * 1_000_000)}
        if any(value is not None for value in usage_event["usage"].values()) or isinstance(
            cost, (int, float)
        ):
            events.append(usage_event)

        recording_url = artifact.get("recordingUrl") or call.get("recordingUrl")
        if isinstance(recording_url, str) and recording_url:
            events.append(
                _base_event(
                    "vapi",
                    call_id,
                    "recording",
                    "recording.available",
                    ended_at,
                    agent=agent,
                    attributes={
                        "recording_url": recording_url,
                        "recording_external_id": call_id,
                        "media_type": "audio/mpeg",
                    },
                )
            )

    if not events:
        status = "error" if "error" in event_name.lower() else "ok"
        event = _base_event(
            "vapi",
            call_id,
            f"provider:{event_name}:{delivery_id}",
            f"vapi.{event_name}",
            message.get("timestamp"),
            agent=agent,
            status=status,
            attributes={"provider_delivery_id": delivery_id},
        )
        if status == "error":
            event["error"] = {
                "type": "VapiWebhookError",
                "message": str(message.get("error") or event_name),
                "retryable": False,
            }
        events.append(event)
    return events


def normalize_retell(
    payload: dict[str, Any], delivery_id: str, config: dict[str, Any] | None = None
) -> list[dict[str, Any]]:
    """Convert Retell lifecycle and analyzed-call snapshots to canonical events."""

    call = payload.get("call", payload)
    if not isinstance(call, dict):
        return []
    call_id = str(call.get("call_id") or call.get("callId") or delivery_id)
    event_name = str(payload.get("event") or payload.get("event_type") or "call_status")
    agent_id = call.get("agent_id") or call.get("agentId")
    agent = _identity(config, agent_id, str(call.get("agent_name") or "Retell agent"))
    started_at = call.get("start_timestamp") or call.get("created_at") or payload.get("timestamp")
    ended_at = call.get("end_timestamp") or payload.get("timestamp")
    events: list[dict[str, Any]] = []

    if event_name == "call_started" or (
        event_name in {"call_ended", "call_analyzed", "call_error"} and started_at is not None
    ):
        events.append(
            _base_event(
                "retell",
                call_id,
                "session-started",
                "session.started",
                started_at,
                agent=agent,
                attributes={"provider_delivery_id": delivery_id},
            )
        )

    if event_name in {"call_ended", "call_analyzed", "call_error"}:
        events.extend(
            _transcript_events(
                "retell",
                call_id,
                call.get("transcript_object"),
                agent=agent,
                started_at=started_at,
            )
        )
        events.extend(
            _tool_events(
                "retell",
                call_id,
                call.get("transcript_object"),
                agent=agent,
                occurred_at=ended_at,
            )
        )
        analysis = call.get("call_analysis") if isinstance(call.get("call_analysis"), dict) else {}
        successful = analysis.get("call_successful")
        reason = call.get("disconnection_reason")
        failed = event_name == "call_error" or (
            isinstance(reason, str) and any(word in reason.lower() for word in ("error", "failed"))
        )
        attributes: dict[str, Any] = {
            "provider_delivery_id": delivery_id,
            "disconnection_reason": reason,
        }
        if successful is not None:
            attributes.update(
                {
                    "outcome": "resolved" if successful else "failed",
                    "outcome_source": "provider",
                }
            )
        terminal = _base_event(
            "retell",
            call_id,
            f"session-ended:{event_name}",
            "session.error" if failed else "session.ended",
            ended_at,
            agent=agent,
            status="error" if failed else "ok",
            attributes=attributes,
        )
        if failed:
            terminal["error"] = {
                "type": "RetellCallError",
                "message": str(reason or "Retell call failed"),
                "retryable": False,
            }
        events.append(terminal)

        latency = call.get("latency") if isinstance(call.get("latency"), dict) else {}
        for key, kind in (
            ("e2e", "voice.response_gap"),
            ("llm", "llm.completed"),
            ("tts", "tts.completed"),
        ):
            value = latency.get(key) or latency.get(f"{key}_latency")
            if isinstance(value, (int, float)):
                latency_event = _base_event(
                    "retell",
                    call_id,
                    f"latency:{key}:{event_name}",
                    kind,
                    ended_at,
                    agent=agent,
                    attributes={"name": f"{key} latency"},
                )
                latency_event["span_id"] = f"retell-{call_id}-{key}"[:64]
                latency_event["duration_ms"] = value
                events.append(latency_event)

        cost = call.get("call_cost") if isinstance(call.get("call_cost"), dict) else {}
        tokens = (
            cost.get("llm_token_usage") if isinstance(cost.get("llm_token_usage"), dict) else {}
        )
        combined_cost = cost.get("combined_cost")
        usage_event = _base_event(
            "retell", call_id, f"usage:{event_name}", "usage.recorded", ended_at, agent=agent
        )
        usage_event["usage"] = {
            "provider": "retell",
            "model": tokens.get("model"),
            "input_tokens": tokens.get("input_tokens"),
            "output_tokens": tokens.get("output_tokens"),
            "total_tokens": tokens.get("total_tokens"),
        }
        if isinstance(combined_cost, (int, float)):
            # Retell reports call cost in cents.
            usage_event["attributes"] = {"provider_cost_micros": round(combined_cost * 10_000)}
        if any(value is not None for value in usage_event["usage"].values()) or isinstance(
            combined_cost, (int, float)
        ):
            events.append(usage_event)

        recording_url = call.get("recording_url")
        if isinstance(recording_url, str) and recording_url:
            events.append(
                _base_event(
                    "retell",
                    call_id,
                    "recording",
                    "recording.available",
                    ended_at,
                    agent=agent,
                    attributes={
                        "recording_url": recording_url,
                        "recording_external_id": call_id,
                        "media_type": "audio/wav",
                    },
                )
            )

    if not events:
        status = "error" if "error" in event_name.lower() else "ok"
        event = _base_event(
            "retell",
            call_id,
            f"provider:{event_name}:{delivery_id}",
            f"retell.{event_name}",
            payload.get("timestamp"),
            agent=agent,
            status=status,
            attributes={"provider_delivery_id": delivery_id},
        )
        if status == "error":
            event["error"] = {
                "type": "RetellWebhookError",
                "message": str(payload.get("error") or event_name),
                "retryable": False,
            }
        events.append(event)
    return events
