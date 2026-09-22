import base64
import hashlib
import json
import secrets
from dataclasses import dataclass

from cryptography.fernet import Fernet, InvalidToken

from voker_voice_api.config import get_settings


@dataclass(frozen=True)
class GeneratedAPIKey:
    raw: str
    prefix: str
    secret_hash: str


def generate_ingest_key(environment: str = "live") -> GeneratedAPIKey:
    """Generate a high-entropy key; persist only its prefix and SHA-256 digest."""

    secret = secrets.token_urlsafe(32)
    prefix = f"vkr_{environment}_{secret[:10]}"
    raw = f"{prefix}_{secret[10:]}"
    return GeneratedAPIKey(raw=raw, prefix=prefix, secret_hash=hash_api_key(raw))


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_webhook_token() -> GeneratedAPIKey:
    """Generate a one-time integration webhook token; persist only its digest."""

    raw = f"vwh_{secrets.token_urlsafe(32)}"
    return GeneratedAPIKey(raw=raw, prefix=raw[:14], secret_hash=hash_api_key(raw))


def _credential_cipher() -> Fernet:
    settings = get_settings()
    secret = settings.credential_encryption_key or settings.session_secret
    if not secret:
        if settings.app_env != "development":
            raise RuntimeError("CREDENTIAL_ENCRYPTION_KEY is required outside development")
        secret = "voker-development-only-connector-key"
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_connector_secrets(values: dict[str, str]) -> str:
    """Encrypt provider credentials before persistence."""

    payload = json.dumps(values, separators=(",", ":"), sort_keys=True).encode()
    return _credential_cipher().encrypt(payload).decode()


def decrypt_connector_secrets(value: str | None) -> dict[str, str]:
    if not value:
        raise ValueError("Integration credentials are unavailable")
    try:
        payload = json.loads(_credential_cipher().decrypt(value.encode()))
    except (InvalidToken, json.JSONDecodeError) as error:
        raise ValueError("Integration credentials could not be decrypted") from error
    if not isinstance(payload, dict) or not all(
        isinstance(key, str) and isinstance(item, str) for key, item in payload.items()
    ):
        raise ValueError("Integration credentials are invalid")
    return payload
