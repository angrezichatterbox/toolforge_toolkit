"""initial tools table

Revision ID: 67ecef2dd332
Revises: 
Create Date: 2026-06-27 15:20:07.167993

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '67ecef2dd332'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'tools',
        sa.Column('id',             sa.String(64),   primary_key=True),
        sa.Column('name',           sa.String(128),  nullable=False),
        sa.Column('tool',           sa.String(64),   nullable=False),
        sa.Column('repo',           sa.String(255),  nullable=False),
        sa.Column('git_url',        sa.String(512),  nullable=False),
        sa.Column('branch',         sa.String(64),   nullable=True, server_default='main'),
        sa.Column('entry_file',     sa.String(128),  nullable=True, server_default='app.py'),
        sa.Column('app_var_name',   sa.String(64),   nullable=True, server_default='app'),
        sa.Column('python_version', sa.String(32),   nullable=True, server_default='python3.11'),
        sa.Column('language',       sa.String(64),   nullable=True),
        sa.Column('description',    sa.Text,         nullable=True),
        sa.Column('url',            sa.String(255),  nullable=True),
        sa.Column('live',           sa.SmallInteger, nullable=True, server_default='0'),
        sa.Column('status',         sa.String(32),   nullable=True, server_default='unknown'),
        sa.Column('last_deploy',    sa.DateTime,     nullable=True),
        sa.Column('sort_order',     sa.Integer,      nullable=True, server_default='0'),
        mysql_engine='InnoDB',
        mysql_charset='utf8mb4',
    )


def downgrade():
    op.drop_table('tools')
