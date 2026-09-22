"""Private recording-delivery helpers.

Audio is never proxied through Voker. The API issues a short-lived Cloudinary
download URL only after the trace-scoped recording lookup has succeeded.
"""

from datetime import UTC, datetime, timedelta
from time import time
from typing import cast
from urllib.parse import urlparse

import cloudinary  # type: ignore[import-untyped]
from cloudinary.utils import private_download_url  # type: ignore[import-untyped]

from voker_voice_api.config import Settings
from voker_voice_api.models import Recording

PLAYBACK_URL_TTL_SECONDS = 300
SUPPORTED_RECORDING_SOURCES = frozenset(
    {"cloudinary", "livekit", "vapi", "retell", "external", "local"}
)
EXTERNAL_RECORDING_SOURCES = frozenset({"livekit", "vapi", "retell", "external"})
SUPPORTED_RECORDING_STATES = frozenset(
    {"available", "processing", "unavailable", "deleted", "expired", "denied"}
)


def validate_recording_metadata(*, source: str, status: str, asset_reference: str | None) -> None:
    if source not in SUPPORTED_RECORDING_SOURCES:
        raise ValueError(f"Unsupported recording source: {source}")
    if status not in SUPPORTED_RECORDING_STATES:
        raise ValueError(f"Unsupported recording status: {status}")
    if status == "available" and not asset_reference:
        raise ValueError("Available recordings require an asset reference")
    if source in EXTERNAL_RECORDING_SOURCES and asset_reference:
        parsed = urlparse(asset_reference)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError("External recording references must use HTTPS")


def recording_expiry(
    expires_at: datetime | None,
    settings: Settings,
    *,
    now: datetime | None = None,
) -> datetime | None:
    if expires_at is not None:
        return expires_at
    if settings.recording_retention_days <= 0:
        return None
    return (now or datetime.now(UTC)) + timedelta(days=settings.recording_retention_days)


def external_playback_url(recording: Recording) -> str:
    if recording.source not in EXTERNAL_RECORDING_SOURCES:
        raise ValueError("Recording is not an external provider asset")
    validate_recording_metadata(
        source=recording.source,
        status=recording.status,
        asset_reference=recording.asset_reference,
    )
    assert recording.asset_reference is not None
    return recording.asset_reference


def cloudinary_playback_url(recording: Recording, settings: Settings) -> str:
    """Create a five-minute authenticated Cloudinary audio URL for one recording."""

    if not all(
        (
            settings.cloudinary_cloud_name,
            settings.cloudinary_api_key,
            settings.cloudinary_api_secret,
        )
    ):
        raise ValueError("Cloudinary credentials are not configured")
    if recording.source != "cloudinary" or not recording.asset_reference:
        raise ValueError("Recording has no Cloudinary asset")

    cloudinary.config(
        cloud_name=settings.cloudinary_cloud_name,
        api_key=settings.cloudinary_api_key,
        api_secret=settings.cloudinary_api_secret,
        secure=True,
    )
    media_format = "mp3" if recording.media_type == "audio/mpeg" else "wav"
    return cast(
        str,
        private_download_url(
            recording.asset_reference,
            media_format,
            resource_type="video",  # Cloudinary stores audio under the video resource type.
            type="authenticated",
            expires_at=int(time()) + PLAYBACK_URL_TTL_SECONDS,
        ),
    )
