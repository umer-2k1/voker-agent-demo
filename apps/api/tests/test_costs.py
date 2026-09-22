from voker_voice_api.costs import RATE_CARDS, RateCard, estimate_llm_cost_micros


def test_unknown_models_are_not_costed() -> None:
    assert (
        estimate_llm_cost_micros(
            provider="openrouter", model="unknown", input_tokens=1, output_tokens=1
        )
        is None
    )


def test_rate_card_costs_tokens_without_rounding_up() -> None:
    RATE_CARDS[("test", "model")] = RateCard("test-v1", 1_000_000, 2_000_000)
    assert (
        estimate_llm_cost_micros(provider="test", model="model", input_tokens=3, output_tokens=2)[0]
        == 7
    )


def test_supported_development_model_uses_versioned_cached_token_rate() -> None:
    amount, card = estimate_llm_cost_micros(
        provider="openrouter",
        model="openai/gpt-4o-mini",
        input_tokens=1_000_000,
        cached_tokens=500_000,
        output_tokens=1_000_000,
    ) or (None, None)

    assert amount == 712_500
    assert card is not None
    assert card.version == "openai-gpt-4o-mini-2026-09-22"


def test_zero_usage_produces_a_zero_cost_record_value() -> None:
    estimate = estimate_llm_cost_micros(
        provider="openai", model="gpt-4o-mini", input_tokens=0, output_tokens=0
    )

    assert estimate is not None
    assert estimate[0] == 0
