from voker_voice_api.connectors import normalize_retell, normalize_vapi


def test_vapi_normalization_is_stable() -> None:
    event = normalize_vapi(
        {"message": {"type": "end-of-call-report", "call": {"id": "call-1"}}}, "delivery-1"
    )[0]
    assert event["external_session_id"] == "call-1"
    assert event["source"]["integration"] == "vapi"


def test_retell_error_normalization_has_error_payload() -> None:
    event = normalize_retell({"event": "call_error", "call": {"call_id": "call-2"}}, "delivery-2")[
        0
    ]
    assert event["status"] == "error"
    assert event["error"]["type"] == "RetellWebhookError"
