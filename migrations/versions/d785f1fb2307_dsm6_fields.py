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
    with op.batch_alter_table("screenshot") as batch_op:
        batch_op.alter_column(
            "path",
            existing_type=sa.VARCHAR(length=100),
            type_=sa.Unicode(length=200),
            existing_nullable=False,
        )
    with op.batch_alter_table("version") as batch_op:
        batch_op.add_column(
            sa.Column("conf_privilege", sa.Unicode(length=255), nullable=True)
        )
        batch_op.add_column(
            sa.Column("conf_resource", sa.Unicode(length=255), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("version") as batch_op:
        batch_op.drop_column("conf_resource")
        batch_op.drop_column("conf_privilege")
    with op.batch_alter_table("screenshot") as batch_op:
        batch_op.alter_column(
            "path",
            existing_type=sa.Unicode(length=200),
            type_=sa.VARCHAR(length=100),
            existing_nullable=False,
        )
