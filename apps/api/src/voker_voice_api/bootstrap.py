from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.models import Agent, APIKey, Environment, Organization, Project
from voker_voice_api.security import GeneratedAPIKey, generate_ingest_key

DEVELOPMENT_ORGANIZATION = "Voker Development"
DEVELOPMENT_PROJECT_SLUG = "voker-voice"
DEVELOPMENT_ENVIRONMENT_SLUG = "development"
DEVELOPMENT_AGENT_SLUG = "support-agent"


def ensure_development_seed(db: Session) -> tuple[Organization, Project, Environment, Agent]:
    """Create the non-secret local development ownership hierarchy idempotently."""

    organization = db.scalar(
        select(Organization).where(Organization.name == DEVELOPMENT_ORGANIZATION)
    )
    if organization is None:
        organization = Organization(name=DEVELOPMENT_ORGANIZATION)
        db.add(organization)
        db.flush()

    project = db.scalar(
        select(Project).where(
            Project.organization_id == organization.id,
            Project.slug == DEVELOPMENT_PROJECT_SLUG,
        )
    )
    if project is None:
        project = Project(
            organization_id=organization.id,
            name="Voker Voice",
            slug=DEVELOPMENT_PROJECT_SLUG,
        )
        db.add(project)
        db.flush()

    environment = db.scalar(
        select(Environment).where(
            Environment.project_id == project.id,
            Environment.slug == DEVELOPMENT_ENVIRONMENT_SLUG,
        )
    )
    if environment is None:
        environment = Environment(
            project_id=project.id,
            name="Development",
            slug=DEVELOPMENT_ENVIRONMENT_SLUG,
            kind="development",
        )
        db.add(environment)
        db.flush()

    agent = db.scalar(
        select(Agent).where(
            Agent.project_id == project.id,
            Agent.slug == DEVELOPMENT_AGENT_SLUG,
        )
    )
    if agent is None:
        agent = Agent(
            project_id=project.id,
            name="Support Agent",
            slug=DEVELOPMENT_AGENT_SLUG,
            source="custom",
        )
        db.add(agent)
        db.flush()

    return organization, project, environment, agent


def create_ingest_key(
    db: Session, *, project: Project, environment: Environment, label: str
) -> GeneratedAPIKey:
    """Create a project/environment scoped key and return its raw value once."""

    generated = generate_ingest_key("live" if environment.kind == "production" else "test")
    db.add(
        APIKey(
            project_id=project.id,
            environment_id=environment.id,
            label=label,
            prefix=generated.prefix,
            secret_hash=generated.secret_hash,
        )
    )
    db.flush()
    return generated
