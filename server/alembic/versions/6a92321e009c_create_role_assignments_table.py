"""create role_assignments table

Revision ID: 6a92321e009c
Revises: 59b5f0643dbd
Create Date: 2026-10-29 14:33:12.638464

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6a92321e009c'
down_revision: Union[str, Sequence[str], None] = '59b5f0643dbd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'role_assignments',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='active'),
        sa.Column('granted_by', sa.String(length=36), nullable=True),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('revoked_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('onchain_tx_hash', sa.String(length=66), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['granted_by'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'role', name='uq_user_role')
    )
    op.create_index(op.f('ix_role_assignments_user_id'), 'role_assignments', ['user_id'], unique=False)
    op.create_index(op.f('ix_role_assignments_role'), 'role_assignments', ['role'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_role_assignments_role'), table_name='role_assignments')
    op.drop_index(op.f('ix_role_assignments_user_id'), table_name='role_assignments')
    op.drop_table('role_assignments')
