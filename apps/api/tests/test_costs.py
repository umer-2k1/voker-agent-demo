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
