from unittest.mock import MagicMock

from voker_voice_api.bootstrap import ensure_development_seed


def test_seed_adds_records_when_all_entities_are_missing() -> None:
    db = MagicMock()
    db.scalar.side_effect = [None, None, None, None]

    organization, project, environment, agent = ensure_development_seed(db)

    assert organization.name == "Voker Development"
    assert project.slug == "voker-voice"
    assert environment.slug == "development"
    assert agent.slug == "support-agent"
    assert db.add.call_count == 4
    assert db.flush.call_count == 4
