"""Small, evidence-bounded Voice Impact cohort calculations."""

from collections.abc import Iterable
from dataclasses import dataclass

MINIMUM_COHORT_SIZE = 5


@dataclass(frozen=True)
class CohortValue:
    key: str
    outcome: str | None
    interruption_count: int
    stt_duration_ms: float | None
    dead_air_count: int = 0


def resolution_rate(values: Iterable[CohortValue]) -> dict[str, int | float] | None:
    observed = [value for value in values if value.outcome is not None]
    if len(observed) < MINIMUM_COHORT_SIZE:
        return None
    resolved = sum(value.outcome in {"success", "resolved"} for value in observed)
    return {
        "sample_size": len(observed),
        "resolved": resolved,
        "resolution_rate": resolved / len(observed),
    }


def voice_impact_cohorts(values: Iterable[CohortValue]) -> dict[str, dict[str, int | float] | None]:
    rows = list(values)
    return {
        "high_interruption": resolution_rate(
            value for value in rows if value.interruption_count >= 3
        ),
        "normal_interruption": resolution_rate(
            value for value in rows if value.interruption_count <= 1
        ),
        "slow_stt": resolution_rate(
            value
            for value in rows
            if value.stt_duration_ms is not None and value.stt_duration_ms > 1200
        ),
        "fast_stt": resolution_rate(
            value
            for value in rows
            if value.stt_duration_ms is not None and value.stt_duration_ms <= 500
        ),
        "dead_air": resolution_rate(value for value in rows if value.dead_air_count >= 1),
        "no_dead_air": resolution_rate(value for value in rows if value.dead_air_count == 0),
    }


def latency_distribution(values: Iterable[float]) -> dict[str, float | int] | None:
    """Return transparent percentile summary values without inventing missing latency."""

    ordered = sorted(values)
    if not ordered:
        return None

    def percentile(percent: float) -> float:
        index = round((len(ordered) - 1) * percent)
        return ordered[index]

    return {
        "sample_size": len(ordered),
        "p50_ms": percentile(0.5),
        "p95_ms": percentile(0.95),
        "max_ms": ordered[-1],
    }
