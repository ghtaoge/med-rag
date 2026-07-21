"""Create privacy-preserving safety events."""

from alembic import op
import sqlalchemy as sa

revision = "20260722_03"
down_revision = "20260722_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "safety_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("department_ids_json", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("input_hash", sa.String(64), nullable=False),
        sa.Column("redacted_excerpt", sa.String(300), nullable=False),
        sa.Column("risk_level", sa.String(16), nullable=False),
        sa.Column("categories_json", sa.Text(), nullable=False),
        sa.Column("decision", sa.String(32), nullable=False),
        sa.Column("policy_version", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column in (
        "user_id",
        "request_id",
        "input_hash",
        "risk_level",
        "decision",
        "created_at",
    ):
        op.create_index(f"ix_safety_events_{column}", "safety_events", [column])


def downgrade() -> None:
    op.drop_table("safety_events")
