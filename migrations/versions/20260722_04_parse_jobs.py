"""Create durable quarantined document parse jobs."""

from alembic import op
import sqlalchemy as sa

revision = "20260722_04"
down_revision = "20260722_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "parse_jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_id",
            sa.String(36),
            sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("knowledge_document_versions.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("quarantine_storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("parsed_storage_key", sa.String(512)),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("error_code", sa.String(64)),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(128)),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("parser_name", sa.String(128)),
        sa.Column("parser_version", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_parse_jobs_document_id", "parse_jobs", ["document_id"])
    op.create_index(
        "ix_parse_jobs_document_version_id", "parse_jobs", ["document_version_id"]
    )
    op.create_index("ix_parse_jobs_status", "parse_jobs", ["status"])
    op.create_index("ix_parse_jobs_created_at", "parse_jobs", ["created_at"])


def downgrade() -> None:
    op.drop_table("parse_jobs")
