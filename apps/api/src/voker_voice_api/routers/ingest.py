import gzip
import json
import uuid
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.auth import authenticate_ingest_key, raw_ingest_key, require_ingest_context
from voker_voice_api.config import get_settings
from voker_voice_api.database import get_db
from voker_voice_api.ingestion import (
    IngestContext,
    ingest_batch,
    session_for_event,
    sse_payload,
)
from voker_voice_api.live import broker
from voker_voice_api.models import Job
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.schemas import (
    CanonicalEvent,
    EventBatchResponse,
    RawEventBatchRequest,
    SessionCreateRequest,
    SessionEndRequest,
)

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
    db.add(
        Job(
            project_id=context.project_id,
            type="run_deterministic_analysis",
            payload={"session_id": str(session.id)},
        )
    )
    db.commit()
    return {"id": str(session.id), "status": session.status}


@router.get("/live/sessions/{external_session_id}")
async def stream_session_events(
    external_session_id: str,
    _: IngestContext = Depends(require_ingest_context),
) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        async for payload in broker.subscribe(external_session_id):
            yield f"event: trace\ndata: {payload}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
