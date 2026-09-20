from datetime import UTC, datetime
from unittest.mock import MagicMock

from voker_voice_api.models import Recording
from voker_voice_api.worker import expire_recordings


def test_expiring_recording_preserves_trace_but_revokes_asset_reference() -> None:
    recording = Recording(
        source="cloudinary", asset_reference="private/voice-call", status="available"
    )
    db = MagicMock()
    db.scalars.return_value = [recording]

    expired = expire_recordings(db, now=datetime.now(UTC))

    assert expired == 1
    assert recording.status == "expired"
    assert recording.asset_reference is None
