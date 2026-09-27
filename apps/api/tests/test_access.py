from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from voker_voice_api.database import Base, get_db
from voker_voice_api.main import app
from voker_voice_api.models import (
    APIKey,
    Environment,
    Organization,
    OrganizationMember,
    Project,
    Recording,
    Span,
    User,
)
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.routers.account import require_dashboard_user
from voker_voice_api.routers.dashboard import project_overview
from voker_voice_api.security import generate_ingest_key


def access_database() -> tuple[Session, User, User, Project, Project, Environment]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    first_org = Organization(name="First")
    second_org = Organization(name="Second")
    owner = User(email="owner@example.test")
    member = User(email="member@example.test")
    db.add_all([first_org, second_org, owner, member])
    db.flush()
    first_project = Project(organization_id=first_org.id, name="First Voice", slug="voice")
    second_project = Project(organization_id=second_org.id, name="Second Voice", slug="voice")
    db.add_all([first_project, second_project])
    db.flush()
    environment = Environment(
        project_id=first_project.id,
        name="Development",
        slug="development",
        kind="development",
    )
    second_environment = Environment(
        project_id=second_project.id,
        name="Development",
        slug="development",
        kind="development",
    )
    db.add_all(
        [
            environment,
            second_environment,
            OrganizationMember(organization_id=first_org.id, user_id=owner.id, role="owner"),
            OrganizationMember(organization_id=first_org.id, user_id=member.id, role="member"),
        ]
    )
    db.commit()
    return db, owner, member, first_project, second_project, environment


def test_dashboard_session_parses_persisted_uuid_and_rejects_invalid_value() -> None:
    db, owner, _, _, _, _ = access_database()

    assert require_dashboard_user(SimpleNamespace(session={"user_id": str(owner.id)}), db) == owner
    with pytest.raises(HTTPException, match="Sign in required") as invalid:
        require_dashboard_user(SimpleNamespace(session={"user_id": "not-a-uuid"}), db)
    assert invalid.value.status_code == 401
    db.close()


def test_project_reads_are_org_scoped_and_slug_collisions_fail_closed() -> None:
    db, owner, _, first_project, second_project, _ = access_database()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_dashboard_user] = lambda: owner
    try:
        client = TestClient(app)
        projects = client.get("/api/projects")
        assert projects.status_code == 200
        assert [item["id"] for item in projects.json()["items"]] == [str(first_project.id)]

        overview = client.get("/api/projects/voice/overview")
        assert overview.status_code == 200
        assert overview.json()["project"]["id"] == str(first_project.id)

        second_org = db.get(Organization, second_project.organization_id)
        assert second_org is not None
        db.add(
            OrganizationMember(
                organization_id=second_org.id,
                user_id=owner.id,
                role="owner",
            )
        )
        db.commit()
        ambiguous = client.get("/api/projects/voice/overview")
        assert ambiguous.status_code == 409
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_members_can_read_but_only_owner_or_admin_can_mutate_keys() -> None:
    db, owner, member, _, _, _ = access_database()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_dashboard_user] = lambda: member
    try:
        client = TestClient(app)
        assert client.get("/api/projects/voice/api-keys").status_code == 200
        denied = client.post(
            "/api/projects/voice/api-keys",
            json={"label": "SDK", "environment": "development"},
        )
        assert denied.status_code == 403
        assert (
            client.post(
                "/api/projects/voice/integrations",
                json={"provider": "vapi", "name": "Vapi"},
            ).status_code
            == 403
        )
        assert (
            client.patch(
                f"/api/projects/voice/integrations/{uuid4()}",
                json={"enabled": False},
            ).status_code
            == 403
        )

        app.dependency_overrides[require_dashboard_user] = lambda: owner
        created = client.post(
            "/api/projects/voice/api-keys",
            json={"label": "SDK", "environment": "development"},
        )
        assert created.status_code == 201
        assert created.json()["api_key"].startswith("vkr_")
        listed = client.get("/api/projects/voice/api-keys")
        assert listed.status_code == 200
        assert listed.json()["items"] == [
            {
                "id": listed.json()["items"][0]["id"],
                "label": "SDK",
                "prefix": created.json()["prefix"],
                "environment": "development",
                "created_at": listed.json()["items"][0]["created_at"],
                "last_used_at": None,
                "revoked_at": None,
            }
        ]
        key = db.scalar(select(APIKey).where(APIKey.prefix == created.json()["prefix"]))
        assert key is not None
        app.dependency_overrides[require_dashboard_user] = lambda: member
        assert client.post(f"/api/projects/voice/api-keys/{key.id}/revoke").status_code == 403
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_owner_can_create_a_read_only_mcp_key_without_changing_ingest_keys() -> None:
    db, owner, member, _, _, _ = access_database()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_dashboard_user] = lambda: member
    try:
        client = TestClient(app, base_url="http://localhost:8001")
        denied = client.post(
            "/api/projects/voice/mcp-keys",
            json={"label": "Codex", "environment": "development"},
        )
        assert denied.status_code == 403

        app.dependency_overrides[require_dashboard_user] = lambda: owner
        created = client.post(
            "/api/projects/voice/mcp-keys",
            json={"label": "Codex", "environment": "development"},
        )
        assert created.status_code == 201
        assert created.json()["api_key"].startswith("vkm_test_")
        assert created.json()["endpoint"].endswith("/mcp")

        listed = client.get("/api/projects/voice/mcp-keys")
        assert listed.status_code == 200
        assert listed.json()["items"][0]["prefix"] == created.json()["prefix"]
        assert listed.json()["items"][0]["scopes"] == ["mcp:read"]

        # The read-only MCP credential must not appear among ingest keys.
        ingest = client.get("/api/projects/voice/api-keys")
        assert ingest.status_code == 200
        assert ingest.json()["items"] == []

        ingest_key = client.post(
            "/api/projects/voice/api-keys",
            json={"label": "SDK", "environment": "development"},
        )
        assert ingest_key.status_code == 201
        ingest_after = client.get("/api/projects/voice/api-keys")
        assert [item["label"] for item in ingest_after.json()["items"]] == ["SDK"]
        mcp_after = client.get("/api/projects/voice/mcp-keys")
        assert [item["label"] for item in mcp_after.json()["items"]] == ["Codex"]
    finally:
        app.dependency_overrides.clear()
        db.close()


def test_project_overview_reconciles_database_side_span_average() -> None:
    db, owner, _, project, _, environment = access_database()
    started_at = datetime.now(UTC)
    voice_session = VoiceSession(
        project_id=project.id,
        environment_id=environment.id,
        external_session_id="overview-call",
        trace_id="overview-trace",
        source="sdk",
        status="completed",
        started_at=started_at,
        metadata_={},
    )
    db.add(voice_session)
    db.flush()
    db.add_all(
        [
            Span(
                session_id=voice_session.id,
                external_span_id=f"span-{index}",
                name="llm",
                kind="llm",
                status="ok",
                started_at=started_at,
                duration_ms=duration,
                attributes={},
            )
            for index, duration in enumerate((100, 300))
        ]
    )
    db.commit()

    overview = project_overview("voice", owner, db)

    assert overview["metrics"]["total_sessions"] == 1
    assert overview["metrics"]["average_span_duration_ms"] == 200
    db.close()


def test_recording_and_live_stream_lookup_cannot_cross_project_or_environment() -> None:
    db, owner, _, first_project, second_project, first_environment = access_database()
    second_environment = db.query(Environment).filter_by(project_id=second_project.id).one()
    other_session = VoiceSession(
        project_id=second_project.id,
        environment_id=second_environment.id,
        external_session_id="shared-call",
        trace_id="other-trace",
        source="sdk",
        status="in_progress",
        started_at=datetime.now(UTC),
        metadata_={},
    )
    db.add(other_session)
    db.flush()
    recording = Recording(
        session_id=other_session.id,
        source="external",
        asset_reference="https://media.example/call.wav",
        status="available",
    )
    generated = generate_ingest_key("test")
    db.add_all(
        [
            recording,
            APIKey(
                project_id=first_project.id,
                environment_id=first_environment.id,
                label="Test",
                prefix=generated.prefix,
                secret_hash=generated.secret_hash,
            ),
        ]
    )
    db.commit()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_dashboard_user] = lambda: owner
    try:
        client = TestClient(app)
        playback = client.get(
            f"/api/projects/voice/sessions/{other_session.id}/recordings/{recording.id}/playback",
            follow_redirects=False,
        )
        assert playback.status_code == 404
        dashboard_live = client.get(f"/api/projects/voice/sessions/{other_session.id}/live")
        assert dashboard_live.status_code == 404
        ingest_live = client.get(
            "/v1/live/sessions/shared-call",
            headers={"Authorization": f"Bearer {generated.raw}"},
        )
        assert ingest_live.status_code == 404
    finally:
        app.dependency_overrides.clear()
        db.close()
