"""create action_tokens table

Revision ID: a344005b4a98
Revises: 771a062d6ab1
Create Date: 2026-10-29 16:22:56.106007

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a344005b4a98'
down_revision: Union[str, Sequence[str], None] = '771a062d6ab1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "action_tokens",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_table(
        "wallet_links",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("address", sa.String(length=64), nullable=False),
        sa.Column("chain_id", sa.Integer(), nullable=False, server_default="84532"),
        sa.Column("wallet_type", sa.String(length=32), nullable=False, server_default="metamask"),
        sa.Column("label", sa.String(length=128), nullable=True),
        sa.Column("passkey_credential_id", sa.String(length=255), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("address", "chain_id", name="uq_wallet_address_chain"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("wallet_links")
    op.drop_table("action_tokens")
