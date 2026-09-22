from voker_voice_api.analytics import CohortValue, latency_distribution, voice_impact_cohorts


def test_voice_impact_omits_small_cohorts() -> None:
    values = [CohortValue(str(index), "success", 3, 1500) for index in range(4)]

    cohorts = voice_impact_cohorts(values)

    assert cohorts["high_interruption"] is None
    assert cohorts["slow_stt"] is None


def test_voice_impact_reports_only_observed_outcomes() -> None:
    values = [
        CohortValue(str(index), "success" if index < 3 else "failed", 3, 1500) for index in range(5)
    ]
    values.append(CohortValue("unknown", None, 3, 1500))

    cohort = voice_impact_cohorts(values)["high_interruption"]

    assert cohort == {"sample_size": 5, "resolved": 3, "resolution_rate": 0.6}


def test_latency_distribution_reports_observed_percentiles() -> None:
    distribution = latency_distribution([10, 20, 30, 40, 50, 60])

    assert distribution == {"sample_size": 6, "p50_ms": 30, "p95_ms": 60, "max_ms": 60}


def test_latency_distribution_keeps_missing_data_unknown() -> None:
    assert latency_distribution([]) is None
