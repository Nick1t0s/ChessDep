"""add social settings, user blocks, notification data, invite delivery status

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-12 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB

revision: str = '0007'
down_revision: Union[str, None] = '0006'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'user_social_settings',
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True, nullable=False),
        sa.Column('presence_mode', sa.Text(), nullable=False, server_default='online'),
        sa.Column('match_invites', sa.Text(), nullable=False, server_default='all'),
        sa.Column('notification_settings', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.CheckConstraint("presence_mode IN ('online', 'dnd')", name='presence_mode_whitelist'),
        sa.CheckConstraint("match_invites IN ('all', 'friends', 'none')", name='match_invites_whitelist'),
    )

    op.create_table(
        'user_blocks',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True, nullable=False),
        sa.Column('blocker_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('blocked_id', sa.BigInteger(), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint('blocker_id != blocked_id', name='check_block_no_self'),
        sa.UniqueConstraint('blocker_id', 'blocked_id', name='uq_user_blocks_blocker_blocked'),
    )
    op.create_index('ix_user_blocks_blocker_id', 'user_blocks', ['blocker_id'])
    op.create_index('ix_user_blocks_blocked_id', 'user_blocks', ['blocked_id'])

    op.add_column(
        'notifications',
        sa.Column('data', JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )

    op.add_column(
        'invite_deliveries',
        sa.Column('status', sa.Text(), nullable=False, server_default='pending'),
    )
    op.create_check_constraint(
        'invite_delivery_status_whitelist',
        'invite_deliveries',
        "status IN ('pending', 'accepted', 'declined')",
    )


def downgrade() -> None:
    op.drop_constraint('invite_delivery_status_whitelist', 'invite_deliveries', type_='check')
    op.drop_column('invite_deliveries', 'status')
    op.drop_column('notifications', 'data')
    op.drop_index('ix_user_blocks_blocked_id', table_name='user_blocks')
    op.drop_index('ix_user_blocks_blocker_id', table_name='user_blocks')
    op.drop_table('user_blocks')
    op.drop_table('user_social_settings')
