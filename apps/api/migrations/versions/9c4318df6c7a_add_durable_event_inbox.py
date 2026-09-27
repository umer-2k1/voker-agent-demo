"""add durable event inbox and capture state

Revision ID: 9c4318df6c7a
Revises: f03c2d6a9b21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "9c4318df6c7a"
down_revision: str | Sequence[str] | None = "f03c2d6a9b21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

json_value = sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    op.create_table(
        "raw_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("external_session_id", sa.String(length=255), nullable=False),
        sa.Column("event_id", sa.String(length=64), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(length=128), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", json_value, nullable=False),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("projected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("projection_attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("projection_error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "event_id", name="uq_raw_event_project_event_id"),
        sa.UniqueConstraint(
            "project_id",
            "environment_id",
            "external_session_id",
            "sequence",
            name="uq_raw_event_session_sequence",
        ),
    )
    op.create_index(
        "ix_raw_events_projection",
        "raw_events",
        ["project_id", "environment_id", "external_session_id", "projected_at", "sequence"],
    )
    op.create_table(
        "session_capture_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("project_id", sa.Uuid(), nullable=False),
        sa.Column("environment_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=True),
        sa.Column("external_session_id", sa.String(length=255), nullable=False),
        sa.Column("state", sa.String(length=32), server_default="receiving", nullable=False),
        sa.Column("highest_seen_sequence", sa.Integer(), nullable=True),
        sa.Column("highest_contiguous_sequence", sa.Integer(), nullable=True),
        sa.Column("expected_last_sequence", sa.Integer(), nullable=True),
        sa.Column("missing_ranges", json_value, server_default="[]", nullable=False),
        sa.Column("raw_event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("projected_event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("permanent_rejection_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column("projected_generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "last_received_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locked_by", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(["environment_id"], ["environments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "project_id",
            "environment_id",
            "external_session_id",
            name="uq_capture_external_session",
        ),
    )
    op.create_index(
        "ix_capture_pending",
        "session_capture_states",
        ["state", "projected_generation", "generation"],
    )


def downgrade() -> None:
    op.drop_index("ix_capture_pending", table_name="session_capture_states")
    op.drop_table("session_capture_states")
    op.drop_index("ix_raw_events_projection", table_name="raw_events")
    op.drop_table("raw_events")
