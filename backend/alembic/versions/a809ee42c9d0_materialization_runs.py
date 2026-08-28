"""materialization_runs

Revision ID: a809ee42c9d0
Revises: 001
Create Date: 2026-08-28 15:09:03.068917

"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = 'a809ee42c9d0'
down_revision = '001'
branch_labels = None
depends_on = None

# `artifact_status` already exists (created in 001 and shared by parsing_results,
# chunk_results, index_builds). Reference it with `create_type=False` so this migration
# reuses the type instead of emitting a second CREATE TYPE, which would fail.
ARTIFACT_STATUS = postgresql.ENUM(
    'pending', 'running', 'ready', 'failed',
    name='artifact_status', create_type=False,
)


def upgrade() -> None:
    op.create_table('materialization_runs',
    sa.Column('chunking_configuration_id', sa.UUID(), nullable=False),
    sa.Column('corpus_id', sa.UUID(), nullable=True),
    sa.Column('workflow_id', sa.Text(), nullable=False),
    sa.Column('status', ARTIFACT_STATUS, server_default='pending', nullable=False),
    sa.Column('document_count', sa.Integer(), nullable=False),
    sa.Column('progress', postgresql.JSONB(astext_type=sa.Text()), server_default='{}', nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('id', sa.UUID(), server_default=sa.text('gen_random_uuid()'), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['chunking_configuration_id'], ['chunking_configurations.id'], name=op.f('fk_materialization_runs_chunking_configuration_id_chunking_configurations'), ondelete='RESTRICT'),
    sa.ForeignKeyConstraint(['corpus_id'], ['corpora.id'], name=op.f('fk_materialization_runs_corpus_id_corpora'), ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id', name=op.f('pk_materialization_runs')),
    sa.UniqueConstraint('workflow_id', name=op.f('uq_materialization_runs_workflow_id'))
    )
    op.create_index(op.f('ix_materialization_runs_chunking_configuration_id'), 'materialization_runs', ['chunking_configuration_id'], unique=False)
    op.create_index(op.f('ix_materialization_runs_corpus_id'), 'materialization_runs', ['corpus_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_materialization_runs_corpus_id'), table_name='materialization_runs')
    op.drop_index(op.f('ix_materialization_runs_chunking_configuration_id'), table_name='materialization_runs')
    op.drop_table('materialization_runs')

