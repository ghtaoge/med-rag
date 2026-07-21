"""Create local identity, department membership, refresh token, and audit tables."""

from alembic import op
import sqlalchemy as sa

revision = "20260722_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("username", sa.String(128), nullable=False),
        sa.Column("password_hash", sa.String(512), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("must_change_password", sa.Boolean(), nullable=False),
        sa.Column("failed_login_count", sa.Integer(), nullable=False),
        sa.Column("locked_until", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("username", name="uq_users_username"),
    )
    op.create_index("ix_users_username", "users", ["username"], unique=True)
    op.create_table(
        "departments",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.UniqueConstraint("name", name="uq_departments_name"),
    )
    op.create_table(
        "department_memberships",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department_id", sa.String(36), sa.ForeignKey("departments.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False),
        sa.UniqueConstraint("user_id", "department_id", name="uq_membership_user_department"),
    )
    op.create_index("ix_memberships_user", "department_memberships", ["user_id"])
    op.create_index("ix_memberships_department", "department_memberships", ["department_id"])
    op.create_table(
        "refresh_token_families",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("last_rotated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_refresh_user", "refresh_token_families", ["user_id"])
    op.create_table(
        "audit_events",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("actor_user_id", sa.String(36)),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("resource_type", sa.String(64), nullable=False),
        sa.Column("resource_id", sa.String(128), nullable=False),
        sa.Column("result", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("request_id", sa.String(64), nullable=False),
        sa.Column("before_state_hash", sa.String(64)),
        sa.Column("after_state_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_audit_actor", "audit_events", ["actor_user_id"])
    op.create_index("ix_audit_action", "audit_events", ["action"])
    op.create_index("ix_audit_created", "audit_events", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_table("refresh_token_families")
    op.drop_table("department_memberships")
    op.drop_table("departments")
    op.drop_table("users")
