from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SpanStatus(StrEnum):
    UNSET = "unset"
    OK = "ok"
    ERROR = "error"
    CANCELLED = "cancelled"
    TIMEOUT = "timeout"


class AgentIdentity(BaseModel):
    id: str | None = None
    name: str | None = Field(default=None, max_length=255)
    version: str | None = Field(default=None, max_length=255)


class SourceIdentity(BaseModel):
    integration: str | None = Field(default=None, max_length=64)
    provider: str | None = Field(default=None, max_length=64)
    sdk: str | None = Field(default=None, max_length=128)
    sdk_version: str | None = Field(default=None, max_length=64)


class ErrorPayload(BaseModel):
    type: str = Field(min_length=1, max_length=255)
    code: str | None = Field(default=None, max_length=255)
    message: str = Field(min_length=1, max_length=10_000)
    retryable: bool = False
    retry_count: int = Field(default=0, ge=0)
    provider_request_id: str | None = Field(default=None, max_length=255)
    stacktrace: str | None = Field(default=None, max_length=50_000)


class UsagePayload(BaseModel):
    provider: str | None = None
    model: str | None = None
    input_tokens: int | None = Field(default=None, ge=0)
    output_tokens: int | None = Field(default=None, ge=0)
    cached_tokens: int | None = Field(default=None, ge=0)
    total_tokens: int | None = Field(default=None, ge=0)
    audio_seconds: float | None = Field(default=None, ge=0)
    tts_characters: int | None = Field(default=None, ge=0)


class CanonicalEvent(BaseModel):
    """Provider-independent event accepted by the Voker Voice ingestion API."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^1\.\d+$")
    event_id: str = Field(min_length=1, max_length=64)
    event_type: str = Field(min_length=1, max_length=128)
    occurred_at: datetime
    sequence: int | None = Field(default=None, ge=0)
    external_session_id: str = Field(min_length=1, max_length=255)
    trace_id: str = Field(min_length=1, max_length=64)
    span_id: str | None = Field(default=None, max_length=64)
    parent_span_id: str | None = Field(default=None, max_length=64)
    turn_id: str | None = Field(default=None, max_length=64)
    agent_run_id: str | None = Field(default=None, max_length=64)
    agent: AgentIdentity | None = None
    source: SourceIdentity = Field(default_factory=SourceIdentity)
    status: SpanStatus = SpanStatus.UNSET
    duration_ms: float | None = Field(default=None, ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    input: dict[str, Any] | None = None
    output: dict[str, Any] | None = None
    usage: UsagePayload | None = None
    error: ErrorPayload | None = None

    @model_validator(mode="after")
    def validate_status_and_error(self) -> "CanonicalEvent":
        if self.status == SpanStatus.ERROR and self.error is None:
            raise ValueError("error payload is required when status is error")
        if self.error is not None and self.status != SpanStatus.ERROR:
            raise ValueError("status must be error when an error payload is provided")
        return self


class EventBatchRequest(BaseModel):
    schema_version: str = Field(default="1.0", pattern=r"^1\.\d+$")
    events: list[CanonicalEvent] = Field(min_length=1, max_length=500)


class RawEventBatchRequest(BaseModel):
    """Raw batch enables valid items to survive malformed neighbors."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = Field(default="1.0", pattern=r"^1\.\d+$")
    events: list[dict[str, Any]] = Field(min_length=1, max_length=500)


class SessionCreateRequest(BaseModel):
    external_session_id: str = Field(min_length=1, max_length=255)
    trace_id: str = Field(min_length=1, max_length=64)
    source: str = Field(default="custom", max_length=64)
    started_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionEndRequest(BaseModel):
    ended_at: datetime
    status: str = Field(default="completed", max_length=32)
    outcome: str | None = Field(default=None, max_length=32)


class BatchItemResult(BaseModel):
    event_id: str
    status: str
    detail: str | None = None


class EventBatchResponse(BaseModel):
    accepted: int
    duplicate: int
    rejected: int
    items: list[BatchItemResult]
