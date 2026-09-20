from voker_voice_api.analytics import CohortValue, voice_impact_cohorts


def test_voice_impact_omits_small_cohorts() -> None:
    values = [CohortValue(str(index), "success", 3, 1500) for index in range(4)]

    cohorts = voice_impact_cohorts(values)

    assert cohorts["high_interruption"] is None
    assert cohorts["slow_stt"] is None


def test_voice_impact_reports_only_observed_outcomes() -> None:
    values = [
        CohortValue(str(index), "success" if index < 3 else "failed", 3, 1500)
        for index in range(5)
    ]
    values.append(CohortValue("unknown", None, 3, 1500))

    cohort = voice_impact_cohorts(values)["high_interruption"]

    assert cohort == {"sample_size": 5, "resolved": 3, "resolution_rate": 0.6}
