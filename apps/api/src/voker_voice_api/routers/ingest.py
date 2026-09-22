import gzip
import hashlib
import hmac
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.auth import authenticate_ingest_key, raw_ingest_key, require_ingest_context
from voker_voice_api.config import get_settings
from voker_voice_api.connectors import normalize_retell, normalize_vapi, verify_retell_signature
from voker_voice_api.database import get_db
from voker_voice_api.ingestion import (
    IngestContext,
    enqueue_completion_analysis,
    ingest_batch,
    session_for_event,
    sse_payload,
)
from voker_voice_api.live import broker
from voker_voice_api.models import (
    Integration,
    Job,
    Recording,
    WebhookDelivery,
    WebhookReceipt,
)
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.recordings import recording_expiry, validate_recording_metadata
from voker_voice_api.schemas import (
    CanonicalEvent,
    EventBatchResponse,
    RawEventBatchRequest,
    RecordingCreateRequest,
    SessionCreateRequest,
    SessionEndRequest,
    SessionUpdateRequest,
)
from voker_voice_api.security import decrypt_connector_secrets, hash_api_key

router = APIRouter(prefix="/v1", tags=["ingestion"])


async def decode_json_body(request: Request) -> dict[str, Any]:
    body = await request.body()
    settings = get_settings()
    if len(body) > settings.ingest_max_body_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Batch too large"
        )
    if request.headers.get("content-encoding", "").lower() == "gzip":
        try:
            body = gzip.decompress(body)
        except OSError as error:
            raise HTTPException(status_code=400, detail="Invalid gzip request body") from error
        if len(body) > settings.ingest_max_body_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Batch too large"
            )
    try:
        value = json.loads(body)
    except json.JSONDecodeError as error:
        raise HTTPException(status_code=400, detail="Invalid JSON request body") from error
    if not isinstance(value, dict):
        raise HTTPException(status_code=400, detail="JSON body must be an object")
    return value


@router.post("/events/batch", response_model=EventBatchResponse)
async def create_event_batch(
    request: Request,
    db: Session = Depends(get_db),
) -> EventBatchResponse:
    try:
        batch = RawEventBatchRequest.model_validate(await decode_json_body(request))
    except ValidationError as error:
        raise HTTPException(status_code=422, detail=error.errors()) from error
    if len(batch.events) > get_settings().ingest_max_events:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Too many events"
        )

    # Read and validate the potentially-compressed request before querying the database.
    # This keeps the voice SDK responsive when the database has a short transient delay.
    context = authenticate_ingest_key(raw_ingest_key(request), db)
    response = ingest_batch(db, context, batch.events)
    db.commit()
    accepted_ids = {item.event_id for item in response.items if item.status == "accepted"}
    for raw_event in batch.events:
        if raw_event.get("event_id") in accepted_ids:
            event = CanonicalEvent.model_validate(raw_event)
            await broker.publish(event.external_session_id, sse_payload(event))
    return response


async def ingest_webhook(
    request: Request,
    provider: str,
    delivery_id: str,
    db: Session,
) -> EventBatchResponse:
    raw = await decode_json_body(request)
    context = authenticate_ingest_key(raw_ingest_key(request), db)
    events = (
        normalize_vapi(raw, delivery_id)
        if provider == "vapi"
        else normalize_retell(raw, delivery_id)
    )
    response = ingest_batch(db, context, events)
    db.commit()
    return response


@router.post("/webhooks/{provider}/{integration_id}", status_code=status.HTTP_202_ACCEPTED)
async def receive_authenticated_webhook(
    provider: str,
    integration_id: uuid.UUID,
    request: Request,
    x_provider_delivery_id: str | None = Header(default=None),
    x_voker_webhook_token: str | None = Header(default=None),
    x_retell_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    """Durably accept a provider delivery before deferred normalization."""

    if provider not in {"vapi", "retell"}:
        raise HTTPException(status_code=404, detail="Unsupported webhook provider")
    integration = db.get(Integration, integration_id)
    if integration is None or integration.provider != provider or integration.status == "disabled":
        raise HTTPException(status_code=404, detail="Integration not found")
    raw_body = await request.body()
    if provider == "retell":
        try:
            api_key = decrypt_connector_secrets(integration.encrypted_credentials)["api_key"]
        except (KeyError, ValueError) as error:
            raise HTTPException(
                status_code=503, detail="Integration credential unavailable"
            ) from error
        authentic = verify_retell_signature(raw_body, api_key, x_retell_signature)
    else:
        expected = integration.config.get("webhook_token_hash")
        authentic = (
            isinstance(expected, str)
            and isinstance(x_voker_webhook_token, str)
            and hmac.compare_digest(expected, hash_api_key(x_voker_webhook_token))
        )
    if not authentic:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid provider signature"
        )
    raw = await decode_json_body(request)
    delivery_id = (
        x_provider_delivery_id
        or hashlib.sha256(
            json.dumps(raw, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    duplicate = db.scalar(
        select(WebhookReceipt.id).where(
            WebhookReceipt.integration_id == integration.id,
            WebhookReceipt.provider_delivery_id == delivery_id,
        )
    )
    if duplicate is not None:
        return {"status": "duplicate"}
    receipt = WebhookReceipt(
        integration_id=integration.id,
        provider_delivery_id=delivery_id,
        signature_valid=True,
        payload=raw,
    )
    db.add(receipt)
    db.flush()
    db.add(
        Job(
            project_id=integration.project_id,
            type="normalize_webhook",
            payload={"receipt_id": str(receipt.id)},
        )
    )
    if integration.config.get("forwarding_enabled", True):
        destinations = integration.config.get("forwarding_destinations", [])
        if isinstance(destinations, list):
            for destination in destinations:
                if not isinstance(destination, str) or not destination:
                    continue
                delivery = WebhookDelivery(
                    integration_id=integration.id,
                    receipt_id=receipt.id,
                    destination_url=destination,
                    status="pending",
                )
                db.add(delivery)
                db.flush()
                db.add(
                    Job(
                        project_id=integration.project_id,
                        type="forward_webhook",
                        payload={"delivery_id": str(delivery.id)},
                    )
                )
    db.commit()
    return {"status": "accepted"}


@router.post("/webhooks/vapi", response_model=EventBatchResponse)
async def receive_vapi_webhook(
    request: Request,
    x_provider_delivery_id: str = Header(min_length=1),
    db: Session = Depends(get_db),
) -> EventBatchResponse:
    return await ingest_webhook(request, "vapi", x_provider_delivery_id, db)


@router.post("/webhooks/retell", response_model=EventBatchResponse)
async def receive_retell_webhook(
    request: Request,
    x_provider_delivery_id: str = Header(min_length=1),
    db: Session = Depends(get_db),
) -> EventBatchResponse:
    return await ingest_webhook(request, "retell", x_provider_delivery_id, db)


@router.post("/sessions", status_code=status.HTTP_201_CREATED)
async def create_session(
    payload: SessionCreateRequest,
    context: IngestContext = Depends(require_ingest_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    event = CanonicalEvent(
        event_id=f"session-start-{uuid.uuid4()}",
        event_type="session.started",
        occurred_at=payload.started_at,
        external_session_id=payload.external_session_id,
        trace_id=payload.trace_id,
        source={"integration": payload.source},
        attributes=payload.metadata,
        status="ok",
    )
    session = session_for_event(db, context, event)
    db.commit()
    return {"id": str(session.id), "external_session_id": session.external_session_id}


@router.patch("/sessions/{external_session_id}")
def update_session(
    external_session_id: str,
    payload: SessionUpdateRequest,
    context: IngestContext = Depends(require_ingest_context),
    db: Session = Depends(get_db),
) -> dict[str, str | None]:
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == context.project_id,
            VoiceSession.environment_id == context.environment_id,
            VoiceSession.external_session_id == external_session_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    if payload.metadata is not None:
        session.metadata_ = {**session.metadata_, **payload.metadata}
    if payload.outcome is not None:
        session.outcome = payload.outcome
        session.outcome_source = payload.outcome_source or "explicit"
    elif payload.outcome_source is not None:
        session.outcome_source = payload.outcome_source
    db.commit()
    return {"id": str(session.id), "outcome": session.outcome}


@router.post("/sessions/{external_session_id}/end")
async def end_session(
    external_session_id: str,
    payload: SessionEndRequest,
    context: IngestContext = Depends(require_ingest_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == context.project_id,
            VoiceSession.environment_id == context.environment_id,
            VoiceSession.external_session_id == external_session_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    session.status = payload.status
    session.outcome = payload.outcome
    session.ended_at = payload.ended_at
    enqueue_completion_analysis(db, context.project_id, session.id)
    db.commit()
    return {"id": str(session.id), "status": session.status}


@router.post("/recordings", status_code=status.HTTP_201_CREATED)
def create_recording(
    payload: RecordingCreateRequest,
    context: IngestContext = Depends(require_ingest_context),
    db: Session = Depends(get_db),
) -> dict[str, str]:
    session = db.scalar(
        select(VoiceSession).where(
            VoiceSession.project_id == context.project_id,
            VoiceSession.environment_id == context.environment_id,
            VoiceSession.external_session_id == payload.external_session_id,
        )
    )
    if session is None:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        validate_recording_metadata(
            source=payload.source,
            status=payload.status,
            asset_reference=payload.asset_reference,
        )
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    recording = Recording(
        session_id=session.id,
        source=payload.source,
        external_id=payload.external_id,
        asset_reference=(
            None
            if payload.status in {"deleted", "expired", "denied", "unavailable"}
            else payload.asset_reference
        ),
        duration_ms=payload.duration_ms,
        media_type=payload.media_type,
        status=payload.status,
        expires_at=recording_expiry(payload.expires_at, get_settings()),
    )
    db.add(recording)
    db.commit()
    return {"id": str(recording.id), "status": recording.status}


@router.get("/live/sessions/{external_session_id}")
async def stream_session_events(
    external_session_id: str,
    _: IngestContext = Depends(require_ingest_context),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for payload in broker.subscribe(external_session_id):
            yield f"event: trace\ndata: {payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
