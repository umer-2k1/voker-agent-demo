from voker_voice_api.semantic import parse_semantic_result


def test_semantic_parser_accepts_fenced_json() -> None:
    result = parse_semantic_result(
        "```json\n"
        '{"outcome":"failed","summary":"Tool failed.","findings":['
        '{"statement":"Tool error occurred.","severity":"high","confidence":0.9,'
        '"evidence_event_ids":["evt-1"]}]}\n'
        "```"
    )

    assert result.outcome == "failed"
    assert result.findings[0].evidence_event_ids == ["evt-1"]
