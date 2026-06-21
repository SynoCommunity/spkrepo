"""update build path length

Revision ID: d429595e8362
Revises: dc7687894ba7
Create Date: 2022-10-22 21:31:03.050850

"""

import sqlalchemy as sa
from alembic import op

revision = "d429595e8362"
down_revision = "dc7687894ba7"


def upgrade():
    with op.batch_alter_table("build") as batch_op:
        batch_op.alter_column(
            "path",
            existing_type=sa.VARCHAR(length=100),
            type_=sa.Unicode(length=2048),
            existing_nullable=False,
        )


def downgrade():
    # Truncate any paths longer than 100 chars so the column resize succeeds
    bind = op.get_bind()
    if bind.engine.dialect.name == "postgresql":
        op.execute(
            "UPDATE build SET path = substring(path, 1, 100) WHERE length(path) > 100"
        )
    with op.batch_alter_table("build") as batch_op:
        batch_op.alter_column(
            "path",
            existing_type=sa.Unicode(length=2048),
            type_=sa.VARCHAR(length=100),
            existing_nullable=False,
        )
