"""Update for DSM6

Revision ID: a41b2b645a3c
Revises: 26b4c36c11e
Create Date: 2016-12-20 18:30:15.449680

"""
revision = 'a41b2b645a3c'
down_revision = '26b4c36c11e'

from alembic import op
import sqlalchemy as sa



def upgrade():
    op.add_column('version', sa.Column('conf_privilege', sa.Unicode(length=255), nullable=True))
    op.add_column('version', sa.Column('conf_resource', sa.Unicode(length=255), nullable=True))


def downgrade():
    op.drop_column('version', 'conf_resource')
    op.drop_column('version', 'conf_privilege')
