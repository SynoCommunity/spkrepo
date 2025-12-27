"""Update for DSM6, screenshot path adjusted for longer package names

Revision ID: d785f1fb2307
Revises: 26b4c36c11e
Create Date: 2018-04-03 20:18:47.053636

"""

import sqlalchemy as sa
from alembic import op

revision = "d785f1fb2307"
down_revision = "26b4c36c11e"


def upgrade():
    op.alter_column(
        "screenshot",
        "path",
        existing_type=sa.VARCHAR(length=100),
        type_=sa.Unicode(length=200),
        existing_nullable=False,
    )
    op.add_column(
        "version", sa.Column("conf_privilege", sa.Unicode(length=255), nullable=True)
    )
    op.add_column(
        "version", sa.Column("conf_resource", sa.Unicode(length=255), nullable=True)
    )


def downgrade():
    op.drop_column("version", "conf_resource")
    op.drop_column("version", "conf_privilege")
    op.alter_column(
        "screenshot",
        "path",
        existing_type=sa.Unicode(length=200),
        type_=sa.VARCHAR(length=100),
        existing_nullable=False,
    )
