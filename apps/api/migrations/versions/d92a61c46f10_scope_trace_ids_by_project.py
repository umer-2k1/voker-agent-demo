"""scope trace identifiers by project and environment

Revision ID: d92a61c46f10
Revises: cb1f16b2237a
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d92a61c46f10"
down_revision: str | Sequence[str] | None = "cb1f16b2237a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("sessions_trace_id_key", "sessions", type_="unique")
    op.create_unique_constraint(
        "uq_session_project_trace",
        "sessions",
        ["project_id", "environment_id", "trace_id"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_session_project_trace", "sessions", type_="unique")
    op.create_unique_constraint("sessions_trace_id_key", "sessions", ["trace_id"])
