"""Public MCP protocol contract for project-scoped Voker evidence."""

from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from voker_voice_api.database import Base, get_db
from voker_voice_api.main import app
from voker_voice_api.models import APIKey, Environment, Organization, Project
from voker_voice_api.models import Session as VoiceSession
from voker_voice_api.security import generate_mcp_key


def seeded_mcp_database() -> tuple[Session, str]:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    db = Session(engine)
    organization = Organization(name="MCP contract")
    db.add(organization)
    db.flush()
    project = Project(organization_id=organization.id, name="Voice", slug="mcp-contract")
    db.add(project)
    db.flush()
    development = Environment(
        project_id=project.id, name="Development", slug="development", kind="development"
    )
    production = Environment(
        project_id=project.id, name="Production", slug="production", kind="production"
    )
    db.add_all((development, production))
    db.flush()
    generated = generate_mcp_key("test")
    db.add(
        APIKey(
            project_id=project.id,
            environment_id=development.id,
            label="Codex read-only",
            prefix=generated.prefix,
            secret_hash=generated.secret_hash,
            scopes=["mcp:read"],
        )
    )
    db.add_all(
        (
            VoiceSession(
                project_id=project.id,
                environment_id=development.id,
                external_session_id="development-call",
                trace_id="development-trace",
                source="custom",
                status="completed",
                started_at=datetime(2026, 1, 1, tzinfo=UTC),
                metadata_={},
            ),
            VoiceSession(
                project_id=project.id,
                environment_id=production.id,
                external_session_id="production-call",
                trace_id="production-trace",
                source="custom",
                status="failed",
                started_at=datetime(2026, 1, 2, tzinfo=UTC),
                metadata_={},
            ),
        )
    )
    db.commit()
    return db, generated.raw


def test_mcp_requires_a_read_scoped_key_and_lists_only_its_environment(monkeypatch) -> None:
    """A connected MCP host gets Voker tools and cannot cross the key boundary."""

    db, key = seeded_mcp_database()
    monkeypatch.setattr("voker_voice_api.mcp_server.SessionLocal", lambda: db)
    app.dependency_overrides[get_db] = lambda: db
    try:
        with TestClient(app, base_url="http://localhost:8001") as client:
            rejected = client.post(
                "/mcp",
                headers={"accept": "application/json", "content-type": "application/json"},
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "Voker test", "version": "1.0"},
                    },
                },
            )
            assert rejected.status_code == 401

            initialized = client.post(
                "/mcp",
                headers={
                    "authorization": f"Bearer {key}",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2025-11-25",
                        "capabilities": {},
                        "clientInfo": {"name": "Voker test", "version": "1.0"},
                    },
                },
            )
            assert initialized.status_code == 200
            assert initialized.json()["result"]["serverInfo"]["name"] == "Voker Voice"

            tools = client.post(
                "/mcp",
                headers={
                    "authorization": f"Bearer {key}",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={"jsonrpc": "2.0", "id": 3, "method": "tools/list", "params": {}},
            )
            names = {item["name"] for item in tools.json()["result"]["tools"]}
            assert {"get_project", "list_sessions", "get_session_trace"} <= names

            listed = client.post(
                "/mcp",
                headers={
                    "authorization": f"Bearer {key}",
                    "accept": "application/json",
                    "content-type": "application/json",
                },
                json={
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "list_sessions", "arguments": {}},
                },
            )
            payload = listed.json()["result"]["structuredContent"]
            assert [item["external_session_id"] for item in payload["data"]["items"]] == [
                "development-call"
            ]
    finally:
        app.dependency_overrides.clear()
        db.close()
