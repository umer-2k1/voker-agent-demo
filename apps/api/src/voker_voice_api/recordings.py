"""Private recording-delivery helpers.

Audio is never proxied through Voker. The API issues a short-lived Cloudinary
download URL only after the trace-scoped recording lookup has succeeded.
"""

from time import time

import cloudinary
from cloudinary.utils import private_download_url

from voker_voice_api.config import Settings
from voker_voice_api.models import Recording

PLAYBACK_URL_TTL_SECONDS = 300


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
    return private_download_url(
        recording.asset_reference,
        media_format,
        resource_type="video",  # Cloudinary stores audio under the video resource type.
        type="authenticated",
        expires_at=int(time()) + PLAYBACK_URL_TTL_SECONDS,
    )
