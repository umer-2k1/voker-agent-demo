from voker_voice_api.security import generate_ingest_key, hash_api_key


def test_generated_ingest_key_is_hashed_and_prefixed() -> None:
    generated = generate_ingest_key("test")

    assert generated.raw.startswith("vkr_test_")
    assert generated.prefix.startswith("vkr_test_")
    assert generated.secret_hash == hash_api_key(generated.raw)
    assert generated.raw != generated.secret_hash
