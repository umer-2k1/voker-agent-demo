import hashlib
import hmac
import json
from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from voker_voice_api.connectors import (
    configure_provider_resources,
    list_provider_resources,
    normalize_retell,
    normalize_vapi,
    verify_retell_signature,
)
from voker_voice_api.database import Base, get_db
from voker_voice_api.main import app
from voker_voice_api.models import (
    CostRecord,
    Environment,
    Event,
    Integration,
    Job,
    Organization,
    Project,
    Recording,
    Turn,
    WebhookDelivery,
    WebhookReceipt,
)
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.routers.account import require_dashboard_user
from voker_voice_api.security import encrypt_connector_secrets
from voker_voice_api.worker import process_job


def database() -> tuple[Session, Project, Environment]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="Connector Test")
    db.add(organization)
    db.flush()
    project = Project(organization_id=organization.id, name="Voice", slug="voice")
    db.add(project)
    db.flush()
    environment = Environment(
        project_id=project.id, name="Development", slug="development", kind="development"
    )
    db.add(environment)
    db.commit()
    return db, project, environment


def test_provider_clients_validate_list_and_preserve_existing_webhook() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": "assistant-1",
                        "name": "Support",
                        "server": {"url": "https://existing.example/webhook"},
                    }
                ],
            )
        return httpx.Response(200, json={})

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        resources = list_provider_resources("vapi", "secret", client=client)
        forwarding = configure_provider_resources(
            "vapi",
            "secret",
            resources,
            ["assistant-1"],
            webhook_url="https://voker.example/v1/webhooks/vapi/integration",
            webhook_token="vwh_token",
            client=client,
        )

    assert resources[0]["name"] == "Support"
    assert forwarding == ["https://existing.example/webhook"]
    assert requests[0].headers["authorization"] == "Bearer secret"
    configured = json.loads(requests[1].content)
    assert configured["server"]["headers"]["X-Voker-Webhook-Token"] == "vwh_token"


def test_vapi_end_report_normalizes_complete_trace_without_raw_payload_copy() -> None:
    events = normalize_vapi(
        {
            "message": {
                "type": "end-of-call-report",
                "timestamp": "2026-09-21T10:01:00Z",
                "call": {
                    "id": "call-1",
                    "assistantId": "assistant-1",
                    "startedAt": "2026-09-21T10:00:00Z",
                    "endedAt": "2026-09-21T10:01:00Z",
                    "cost": 0.08,
                    "usage": {"promptTokens": 12, "completionTokens": 8},
                    "analysis": {"successEvaluation": True},
                },
                "artifact": {
                    "recordingUrl": "https://media.example/call.mp3",
                    "messages": [
                        {"role": "user", "message": "Where is my order?"},
                        {
                            "role": "assistant",
                            "message": "It ships today.",
                            "toolCallList": [
                                {
                                    "id": "lookup-1",
                                    "name": "lookup_order",
                                    "arguments": {"id": "42"},
                                    "result": {"status": "ready"},
                                }
                            ],
                        },
                    ],
                },
            }
        },
        "delivery-1",
        {"agent_mappings": {"assistant-1": {"name": "Support", "version": "3"}}},
    )

    assert {event["event_type"] for event in events} >= {
        "session.ended",
        "user.transcript.completed",
        "agent.transcript.completed",
        "tool.completed",
        "usage.recorded",
        "recording.available",
    }
    assert all("provider_event" not in event["attributes"] for event in events)
    assert (
        next(event for event in events if event["event_type"] == "session.ended")["attributes"][
            "outcome"
        ]
        == "resolved"
    )


def test_retell_signature_and_unknown_values_are_handled() -> None:
    raw = b'{"event":"call_started","call":{"call_id":"call-2"}}'
    now = datetime(2026, 9, 21, 10, 0, tzinfo=UTC)
    timestamp = str(int(now.timestamp() * 1000))
    digest = hmac.new(b"retell-key", raw + timestamp.encode(), hashlib.sha256).hexdigest()
    assert verify_retell_signature(raw, "retell-key", f"v={timestamp},d={digest}", now=now)
    assert not verify_retell_signature(raw, "wrong-key", f"v={timestamp},d={digest}", now=now)
    event = normalize_retell(json.loads(raw), "delivery-2")[0]
    assert event["event_type"] == "session.started"
    assert "outcome" not in event["attributes"]


def test_managed_connector_workflow_maps_agent_and_reports_health() -> None:
    db, _, _ = database()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_dashboard_user] = lambda: MagicMock()
    resources = [
        {
            "id": "assistant-1",
            "name": "Support",
            "version": "3",
            "existing_webhook_url": "https://existing.example/webhook",
        }
    ]
    try:
        with (
            patch(
                "voker_voice_api.routers.dashboard.list_provider_resources",
                return_value=resources,
            ),
            patch(
                "voker_voice_api.routers.dashboard.configure_provider_resources",
                return_value=["https://existing.example/webhook"],
            ) as configure,
        ):
            client = TestClient(app)
            connected = client.post(
                "/api/projects/voice/integrations",
                json={"provider": "vapi", "name": "Vapi", "api_key": "private-key"},
            )
            assert connected.status_code == 201
            body = connected.json()
            assert body["status"] == "pending_configuration"
            assert body["webhook_token"] is None

            configured = client.post(
                f"/api/projects/voice/integrations/{body['id']}/configure",
                json={
                    "selected_ids": ["assistant-1"],
                    "public_base_url": "https://voker.example",
                    "environment": "development",
                },
            )
            assert configured.status_code == 200
            assert configured.json()["status"] == "active"
            assert configured.json()["selected_resources"][0]["name"] == "Support"
            assert configured.json()["forwarding_destinations"] == [
                "https://existing.example/webhook"
            ]
            configure.assert_called_once()

            setup = client.get("/api/projects/voice/setup").json()
            assert setup["integrations"][0]["normalization_state"] == "not_yet_observed"
            assert setup["integrations"][0]["selected_resources"][0]["id"] == "assistant-1"

            disabled = client.patch(
                f"/api/projects/voice/integrations/{body['id']}",
                json={"enabled": False, "forwarding_enabled": False},
            )
            assert disabled.json()["status"] == "disabled"
            assert disabled.json()["forwarding_enabled"] is False
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_retell_webhook_is_durable_deduplicated_and_later_analysis_updates_trace() -> None:
    db, project, environment = database()
    api_key = "retell-secret"
    integration = Integration(
        project_id=project.id,
        provider="retell",
        name="Retell",
        status="active",
        encrypted_credentials=encrypt_connector_secrets(
            {"api_key": api_key, "webhook_token": "unused"}
        ),
        config={
            "environment_id": str(environment.id),
            "selected_resources": [{"id": "agent-1", "name": "Support"}],
            "agent_mappings": {"agent-1": {"name": "Support", "version": "4"}},
            "forwarding_enabled": False,
        },
    )
    db.add(integration)
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    client = TestClient(app)

    def send(payload: dict[str, object], delivery_id: str) -> httpx.Response:
        raw = json.dumps(payload, separators=(",", ":")).encode()
        timestamp = str(int(datetime.now(UTC).timestamp() * 1000))
        digest = hmac.new(api_key.encode(), raw + timestamp.encode(), hashlib.sha256).hexdigest()
        return client.post(
            f"/v1/webhooks/retell/{integration.id}",
            content=raw,
            headers={
                "Content-Type": "application/json",
                "X-Retell-Signature": f"v={timestamp},d={digest}",
                "X-Provider-Delivery-Id": delivery_id,
            },
        )

    try:
        started = {
            "event": "call_started",
            "call": {
                "call_id": "call-retell",
                "agent_id": "agent-1",
                "start_timestamp": 1_790_000_000_000,
            },
        }
        assert send(started, "started-1").json()["status"] == "accepted"
        assert send(started, "started-1").json()["status"] == "duplicate"
        first_job = db.scalar(select(Job).where(Job.type == "normalize_webhook"))
        assert first_job is not None
        process_job(db, first_job)
        db.commit()

        analyzed = {
            "event": "call_analyzed",
            "call": {
                "call_id": "call-retell",
                "agent_id": "agent-1",
                "start_timestamp": 1_790_000_000_000,
                "end_timestamp": 1_790_000_060_000,
                "transcript_object": [
                    {"role": "user", "content": "Help me"},
                    {"role": "agent", "content": "Done"},
                ],
                "call_analysis": {"call_successful": True},
                "latency": {"e2e": 420, "llm": 260},
                "call_cost": {
                    "combined_cost": 2.5,
                    "llm_token_usage": {"input_tokens": 20, "output_tokens": 10},
                },
                "recording_url": "https://media.example/retell.wav",
            },
        }
        assert send(analyzed, "analyzed-1").json()["status"] == "accepted"
        latest_receipt = db.scalar(
            select(WebhookReceipt).where(WebhookReceipt.provider_delivery_id == "analyzed-1")
        )
        later_job = next(
            job
            for job in db.scalars(select(Job).where(Job.type == "normalize_webhook"))
            if latest_receipt is not None
            and job.payload.get("receipt_id") == str(latest_receipt.id)
        )
        assert later_job is not None
        process_job(db, later_job)
        db.commit()

        session = db.scalar(select(VoiceSession))
        assert session is not None
        assert session.status == "completed"
        assert session.outcome == "resolved"
        assert db.scalar(select(func.count()).select_from(VoiceSession)) == 1
        assert db.scalar(select(func.count()).select_from(WebhookReceipt)) == 2
        assert db.scalar(select(func.count()).select_from(Turn)) == 2
        assert db.scalar(select(func.count()).select_from(Recording)) == 1
        assert db.scalar(select(CostRecord.amount_micros)) == 25_000
        canonical = db.scalar(select(Event.raw_payload).where(Event.event_type == "session.ended"))
        assert canonical is not None and "provider_event" not in canonical["attributes"]
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_forwarding_job_tracks_success_and_disable_control() -> None:
    db, project, _ = database()
    integration = Integration(
        project_id=project.id,
        provider="vapi",
        name="Vapi",
        status="active",
        config={"forwarding_enabled": True},
    )
    db.add(integration)
    db.flush()
    receipt = WebhookReceipt(
        integration_id=integration.id,
        provider_delivery_id="delivery-1",
        signature_valid=True,
        payload={"message": {"type": "status-update"}},
    )
    db.add(receipt)
    db.flush()
    delivery = WebhookDelivery(
        integration_id=integration.id,
        receipt_id=receipt.id,
        destination_url="https://existing.example/webhook",
    )
    db.add(delivery)
    db.flush()
    job = Job(
        project_id=project.id,
        type="forward_webhook",
        payload={"delivery_id": str(delivery.id)},
        state="running",
        attempt_count=1,
    )
    db.add(job)

    response = MagicMock()
    response.raise_for_status.return_value = None
    with patch("voker_voice_api.worker.httpx.post", return_value=response) as post:
        process_job(db, job)
    assert delivery.status == "succeeded"
    assert delivery.attempt_count == 1
    post.assert_called_once_with(
        "https://existing.example/webhook", json=receipt.payload, timeout=10.0
    )

    integration.status = "disabled"
    second = WebhookDelivery(
        integration_id=integration.id,
        receipt_id=receipt.id,
        destination_url="https://existing.example/webhook",
    )
    db.add(second)
    db.flush()
    process_job(
        db,
        Job(type="forward_webhook", payload={"delivery_id": str(second.id)}),
    )
    assert second.status == "disabled"
