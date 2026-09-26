from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.database import get_db
from voker_voice_api.ingestion import IngestContext
from voker_voice_api.models import APIKey
from voker_voice_api.security import hash_api_key


def raw_ingest_key(request: Request, x_voker_api_key: str | None = Header(default=None)) -> str:
    if x_voker_api_key:
        return x_voker_api_key
    authorization = request.headers.get("authorization", "")
    if authorization.startswith("Bearer "):
        return authorization.removeprefix("Bearer ").strip()
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing Voker ingest key")


def authenticate_ingest_key(key: str, db: Session) -> IngestContext:
    api_key = db.scalar(select(APIKey).where(APIKey.secret_hash == hash_api_key(key)))
    now = datetime.now(UTC)
    if api_key is None or api_key.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Voker ingest key"
        )
    if api_key.expires_at is not None and api_key.expires_at <= now:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Expired Voker ingest key"
        )
    # The ingest path is deliberately read-only with respect to the key row.
    # A voice session emits many concurrent batches using the same key. Touching
    # ``last_used_at`` for every batch makes all of those requests contend for
    # one Postgres row; a single lock timeout then rejects the rest of a call's
    # trace. Last-used reporting is useful account metadata, but it must never
    # sit on the telemetry durability path.
    return IngestContext(api_key=api_key)


def require_ingest_context(
    key: str = Depends(raw_ingest_key), db: Session = Depends(get_db)
) -> IngestContext:
    """Dependency form for routes that do not need to read a request body first."""
    return authenticate_ingest_key(key, db)
