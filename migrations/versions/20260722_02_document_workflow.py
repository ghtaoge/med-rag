"""Create reviewed knowledge document workflow tables."""

from alembic import op
import sqlalchemy as sa

revision = "20260722_02"
down_revision = "20260722_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "knowledge_documents",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_department_id", sa.String(36), sa.ForeignKey("departments.id"), nullable=False),
        sa.Column("visibility", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_documents_owner_department", "knowledge_documents", ["owner_department_id"])
    op.create_table(
        "knowledge_document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("display_name", sa.String(512), nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False, unique=True),
        sa.Column("file_hash", sa.String(64), nullable=False),
        sa.Column("extension", sa.String(32), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("last_edited_by", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reviewed_by", sa.String(36), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("document_id", "version_number", name="uq_document_version"),
    )
    op.create_index("ix_document_versions_document", "knowledge_document_versions", ["document_id"])
    op.create_index("ix_document_versions_status", "knowledge_document_versions", ["status"])
    op.create_table(
        "document_visible_departments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_id", sa.String(36), sa.ForeignKey("knowledge_documents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id", ondelete="CASCADE"), nullable=False),
        sa.UniqueConstraint("document_id", "department_id", name="uq_document_department"),
    )
    op.create_index(
        "ix_document_visible_departments_document_id",
        "document_visible_departments",
        ["document_id"],
    )
    op.create_index(
        "ix_document_visible_departments_department_id",
        "document_visible_departments",
        ["department_id"],
    )
    op.create_table(
        "review_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("document_version_id", sa.String(36), sa.ForeignKey("knowledge_document_versions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("actor_user_id", sa.String(36), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_review_actions_document_version_id",
        "review_actions",
        ["document_version_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_review_actions_document_version_id", table_name="review_actions")
    op.drop_table("review_actions")
    op.drop_index(
        "ix_document_visible_departments_department_id",
        table_name="document_visible_departments",
    )
    op.drop_index(
        "ix_document_visible_departments_document_id",
        table_name="document_visible_departments",
    )
    op.drop_table("document_visible_departments")
    op.drop_table("knowledge_document_versions")
    op.drop_table("knowledge_documents")
