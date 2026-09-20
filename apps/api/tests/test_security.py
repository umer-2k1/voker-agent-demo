from voker_voice_api.security import generate_ingest_key, generate_webhook_token, hash_api_key


def test_generated_ingest_key_is_hashed_and_prefixed() -> None:
    generated = generate_ingest_key("test")

    assert generated.raw.startswith("vkr_test_")
    assert generated.prefix.startswith("vkr_test_")
    assert generated.secret_hash == hash_api_key(generated.raw)
    assert generated.raw != generated.secret_hash


def test_generated_webhook_token_is_hashed_and_not_an_ingest_key() -> None:
    generated = generate_webhook_token()

    assert generated.raw.startswith("vwh_")
    assert generated.secret_hash == hash_api_key(generated.raw)
    assert not generated.raw.startswith("vkr_")
