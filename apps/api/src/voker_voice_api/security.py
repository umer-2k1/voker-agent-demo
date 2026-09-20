import hashlib
import secrets
from dataclasses import dataclass


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
