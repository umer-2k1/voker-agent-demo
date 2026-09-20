"""Versioned, explicit usage cost estimates; unknown models are never guessed."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RateCard:
    version: str
    input_micros_per_million: int
    output_micros_per_million: int


RATE_CARDS: dict[tuple[str, str], RateCard] = {}


def estimate_llm_cost_micros(
    *, provider: str | None, model: str | None, input_tokens: int | None, output_tokens: int | None
) -> tuple[int, RateCard] | None:
    if not provider or not model:
        return None
    card = RATE_CARDS.get((provider, model))
    if card is None:
        return None
    amount = (
        (input_tokens or 0) * card.input_micros_per_million
        + (output_tokens or 0) * card.output_micros_per_million
    ) // 1_000_000
    return amount, card
