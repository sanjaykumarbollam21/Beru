"""baseline schema

Revision ID: 001_baseline
Revises: 
Create Date: 2026-10-25 09:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '001_baseline'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. users
    op.create_table(
        'users',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )

    # 2. devices
    op.create_table(
        'devices',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('platform', sa.String(length=50), nullable=False),
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('capabilities', sa.JSON(), nullable=False),
        sa.Column('last_seen', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_revoked', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_devices_token_hash'), 'devices', ['token_hash'], unique=False)
    op.create_index(op.f('ix_devices_user_id'), 'devices', ['user_id'], unique=False)

    # 3. pairing_codes
    op.create_table(
        'pairing_codes',
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('used', sa.Boolean(), nullable=False),
        sa.Column('approved', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('code')
    )
    op.create_index(op.f('ix_pairing_codes_code'), 'pairing_codes', ['code'], unique=False)
    op.create_index(op.f('ix_pairing_codes_user_id'), 'pairing_codes', ['user_id'], unique=False)

    # 4. user_preferences
    op.create_table(
        'user_preferences',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('key', sa.String(length=100), nullable=False),
        sa.Column('value', sa.JSON(), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_preferences_key'), 'user_preferences', ['key'], unique=False)
    op.create_index(op.f('ix_user_preferences_user_id'), 'user_preferences', ['user_id'], unique=False)

    # 5. user_facts
    op.create_table(
        'user_facts',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('text', sa.String(length=500), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_facts_user_id'), 'user_facts', ['user_id'], unique=False)

    # 6. user_routines
    op.create_table(
        'user_routines',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('steps', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_user_routines_name'), 'user_routines', ['name'], unique=False)
    op.create_index(op.f('ix_user_routines_user_id'), 'user_routines', ['user_id'], unique=False)

    # 7. command_corrections
    op.create_table(
        'command_corrections',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('skill', sa.String(length=100), nullable=False),
        sa.Column('intended_target', sa.String(length=50), nullable=True),
        sa.Column('corrected_target', sa.String(length=50), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.Column('suppressed_until', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_command_corrections_skill'), 'command_corrections', ['skill'], unique=False)
    op.create_index(op.f('ix_command_corrections_user_id'), 'command_corrections', ['user_id'], unique=False)

    # 8. skill_sequence_logs
    op.create_table(
        'skill_sequence_logs',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('sequence_hash', sa.String(length=64), nullable=False),
        sa.Column('sequence_json', sa.JSON(), nullable=False),
        sa.Column('date_str', sa.String(length=10), nullable=False),
        sa.Column('timestamp', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_skill_sequence_logs_date_str'), 'skill_sequence_logs', ['date_str'], unique=False)
    op.create_index(op.f('ix_skill_sequence_logs_sequence_hash'), 'skill_sequence_logs', ['sequence_hash'], unique=False)
    op.create_index(op.f('ix_skill_sequence_logs_user_id'), 'skill_sequence_logs', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_table('skill_sequence_logs')
    op.drop_table('command_corrections')
    op.drop_table('user_routines')
    op.drop_table('user_facts')
    op.drop_table('user_preferences')
    op.drop_table('pairing_codes')
    op.drop_table('devices')
    op.drop_table('users')
