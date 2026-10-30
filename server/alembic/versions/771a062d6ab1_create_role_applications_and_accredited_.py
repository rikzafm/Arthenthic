"""create role_applications and accredited_profiles tables

Revision ID: 771a062d6ab1
Revises: 6a92321e009c
Create Date: 2026-10-29 16:08:57.154975

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '771a062d6ab1'
down_revision: Union[str, Sequence[str], None] = '6a92321e009c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'role_applications',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('requested_role', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), server_default='pending', nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('reviewed_by', sa.String(length=36), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('review_note', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['reviewed_by'], ['users.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_role_applications_user_id'), 'role_applications', ['user_id'], unique=False)
    op.create_index(op.f('ix_role_applications_requested_role'), 'role_applications', ['requested_role'], unique=False)
    op.create_index(op.f('ix_role_applications_status'), 'role_applications', ['status'], unique=False)

    op.create_table(
        'application_documents',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('application_id', sa.String(length=36), nullable=False),
        sa.Column('storage_key', sa.String(length=255), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=True),
        sa.Column('mime', sa.String(length=64), nullable=True),
        sa.Column('sha256', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['application_id'], ['role_applications.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_application_documents_application_id'), 'application_documents', ['application_id'], unique=False)

    op.create_table(
        'accredited_profiles',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('bio_or_org', sa.Text(), nullable=True),
        sa.Column('website', sa.String(length=255), nullable=True),
        sa.Column('verification_notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'role', name='uq_user_profile_role')
    )
    op.create_index(op.f('ix_accredited_profiles_user_id'), 'accredited_profiles', ['user_id'], unique=False)
    op.create_index(op.f('ix_accredited_profiles_role'), 'accredited_profiles', ['role'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('accredited_profiles')
    op.drop_table('application_documents')
    op.drop_table('role_applications')
