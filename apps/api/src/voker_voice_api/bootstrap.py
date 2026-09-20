from sqlalchemy import select
from sqlalchemy.orm import Session

from voker_voice_api.models import Agent, Environment, Organization, Project

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
