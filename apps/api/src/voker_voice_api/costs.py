"""Versioned, explicit usage cost estimates; unknown models are never guessed."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RateCard:
    version: str
    input_micros_per_million: int
    output_micros_per_million: int
    cached_input_micros_per_million: int | None = None
    source: str | None = None


GPT_4O_MINI_2026_09 = RateCard(
    version="openai-gpt-4o-mini-2026-09-22",
    input_micros_per_million=150_000,
    output_micros_per_million=600_000,
    cached_input_micros_per_million=75_000,
    source="https://developers.openai.com/api/docs/models/gpt-4o-mini",
)
GPT_4_1_MINI_2026_09 = RateCard(
    version="openai-gpt-4.1-mini-2026-09-22",
    input_micros_per_million=400_000,
    output_micros_per_million=1_600_000,
    cached_input_micros_per_million=100_000,
    source="https://developers.openai.com/api/docs/models/gpt-4.1-mini",
)

# Static cards are intentionally narrow and versioned. Provider-reported cost
# always wins; unknown models stay unknown instead of receiving a guessed rate.
RATE_CARDS: dict[tuple[str, str], RateCard] = {
    ("openai", "gpt-4o-mini"): GPT_4O_MINI_2026_09,
    ("openrouter", "openai/gpt-4o-mini"): GPT_4O_MINI_2026_09,
    ("openrouter", "openai/gpt-4o-mini-2024-07-18"): GPT_4O_MINI_2026_09,
    ("openai", "gpt-4.1-mini"): GPT_4_1_MINI_2026_09,
    ("openai", "gpt-4.1-mini-2025-04-14"): GPT_4_1_MINI_2026_09,
    ("openrouter", "openai/gpt-4.1-mini"): GPT_4_1_MINI_2026_09,
}


def estimate_llm_cost_micros(
    *,
    provider: str | None,
    model: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    cached_tokens: int | None = None,
) -> tuple[int, RateCard] | None:
    if not provider or not model:
        return None
    card = RATE_CARDS.get((provider, model))
    if card is None:
        return None
    input_count = input_tokens or 0
    cached_count = min(input_count, cached_tokens or 0)
    regular_input_count = input_count - cached_count
    cached_rate = card.cached_input_micros_per_million or card.input_micros_per_million
    amount = (
        regular_input_count * card.input_micros_per_million
        + cached_count * cached_rate
        + (output_tokens or 0) * card.output_micros_per_million
    ) // 1_000_000
    return amount, card
