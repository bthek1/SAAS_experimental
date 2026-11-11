"""Baseline: the schema Django's catalog migrations left (#35).

Revision ID: 0001
Revises:
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = '0001'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('accounts_customuser',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('password', sa.String(length=128), nullable=False),
    sa.Column('last_login', sa.DateTime(timezone=True), nullable=True),
    sa.Column('is_superuser', sa.Boolean(), nullable=False),
    sa.Column('first_name', sa.String(length=150), nullable=False),
    sa.Column('last_name', sa.String(length=150), nullable=False),
    sa.Column('email', sa.String(length=254), nullable=False),
    sa.Column('is_staff', sa.Boolean(), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('date_joined', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email', name='accounts_customuser_email_4fd8e7ce_uniq')
    )
    op.create_index('accounts_customuser_email_4fd8e7ce_like', 'accounts_customuser', ['email'], unique=False, postgresql_ops={'email': 'varchar_pattern_ops'})
    op.create_table('catalog_outboxevent',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('event_type', sa.String(length=64), nullable=False),
    sa.Column('aggregate_id', sa.Uuid(), nullable=False),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('data', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('attempts', sa.Integer(), nullable=False),
    sa.Column('last_error', sa.Text(), nullable=False),
    sa.CheckConstraint('attempts >= 0', name='catalog_outboxevent_attempts_check'),
    sa.CheckConstraint('version >= 0', name='catalog_outboxevent_version_check'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('outbox_pending', 'catalog_outboxevent', ['created_at'], unique=False, postgresql_where=sa.text('delivered_at IS NULL'), sqlite_where=sa.text('delivered_at IS NULL'))
    op.create_table('questionnaires_batterytype',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('description', sa.Text(), nullable=False),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('version >= 0', name='questionnaires_batterytype_version_check'),
    sa.ForeignKeyConstraint(['owner_id'], ['accounts_customuser.id'], name='questionnaires_batte_owner_id_37d17dd4_fk_accounts_', initially='DEFERRED', deferrable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('questionnai_owner_i_8141dc_idx', 'questionnaires_batterytype', ['owner_id', sa.literal_column('created_at DESC')], unique=False)
    op.create_index('questionnaires_batterytype_owner_id_37d17dd4', 'questionnaires_batterytype', ['owner_id'], unique=False)
    op.create_table('questionnaires_questionnairetype',
    sa.Column('id', sa.Uuid(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('questionnaire_json', sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), 'postgresql'), nullable=False),
    sa.Column('version', sa.BigInteger(), nullable=False),
    sa.Column('owner_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('version >= 0', name='questionnaires_questionnairetype_version_check'),
    sa.ForeignKeyConstraint(['owner_id'], ['accounts_customuser.id'], name='questionnaires_quest_owner_id_33ca2bd1_fk_accounts_', initially='DEFERRED', deferrable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('questionnai_owner_i_be24a4_idx', 'questionnaires_questionnairetype', ['owner_id', sa.literal_column('created_at DESC')], unique=False)
    op.create_index('questionnaires_questionnairetype_owner_id_33ca2bd1', 'questionnaires_questionnairetype', ['owner_id'], unique=False)
    op.create_table('questionnaires_batterytypeitem',
    sa.Column('id', sa.BigInteger().with_variant(sa.Integer(), 'sqlite'), sa.Identity(always=False), nullable=False),
    sa.Column('order', sa.Integer(), nullable=False),
    sa.Column('battery_type_id', sa.Uuid(), nullable=False),
    sa.Column('questionnaire_type_id', sa.Uuid(), nullable=False),
    sa.CheckConstraint('"order" >= 0', name='questionnaires_batterytypeitem_order_check'),
    sa.ForeignKeyConstraint(['battery_type_id'], ['questionnaires_batterytype.id'], name='questionnaires_batte_battery_type_id_fd206f4c_fk_questionn', initially='DEFERRED', deferrable=True),
    sa.ForeignKeyConstraint(['questionnaire_type_id'], ['questionnaires_questionnairetype.id'], name='questionnaires_batte_questionnaire_type_i_7c7803cd_fk_questionn', initially='DEFERRED', deferrable=True),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('battery_type_id', 'order', name='questionnaires_batteryty_battery_type_id_order_dcdbcc78_uniq')
    )
    op.create_index('questionnaires_batterytypeitem_battery_type_id_fd206f4c', 'questionnaires_batterytypeitem', ['battery_type_id'], unique=False)
    op.create_index('questionnaires_batterytypeitem_questionnaire_type_id_7c7803cd', 'questionnaires_batterytypeitem', ['questionnaire_type_id'], unique=False)


def downgrade() -> None:
    op.drop_index('questionnaires_batterytypeitem_questionnaire_type_id_7c7803cd', table_name='questionnaires_batterytypeitem')
    op.drop_index('questionnaires_batterytypeitem_battery_type_id_fd206f4c', table_name='questionnaires_batterytypeitem')
    op.drop_table('questionnaires_batterytypeitem')
    op.drop_index('questionnaires_questionnairetype_owner_id_33ca2bd1', table_name='questionnaires_questionnairetype')
    op.drop_index('questionnai_owner_i_be24a4_idx', table_name='questionnaires_questionnairetype')
    op.drop_table('questionnaires_questionnairetype')
    op.drop_index('questionnaires_batterytype_owner_id_37d17dd4', table_name='questionnaires_batterytype')
    op.drop_index('questionnai_owner_i_8141dc_idx', table_name='questionnaires_batterytype')
    op.drop_table('questionnaires_batterytype')
    op.drop_index('outbox_pending', table_name='catalog_outboxevent', postgresql_where=sa.text('delivered_at IS NULL'), sqlite_where=sa.text('delivered_at IS NULL'))
    op.drop_table('catalog_outboxevent')
    op.drop_index('accounts_customuser_email_4fd8e7ce_like', table_name='accounts_customuser', postgresql_ops={'email': 'varchar_pattern_ops'})
    op.drop_table('accounts_customuser')
