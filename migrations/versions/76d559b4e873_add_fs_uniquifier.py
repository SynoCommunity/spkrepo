"""Add fs_uniquifier

Revision ID: 76d559b4e873
Revises: d429595e8362
Create Date: 2022-10-24 09:31:01.814928

"""

import sqlalchemy as sa
from alembic import op

revision = "76d559b4e873"
down_revision = "d429595e8362"


def upgrade():
    is_pg = op.get_bind().engine.dialect.name == "postgresql"
    with op.batch_alter_table("user") as batch_op:
        batch_op.add_column(
            sa.Column(
                "fs_uniquifier",
                sa.String(length=255),
                nullable=False,
                server_default=sa.text("md5(random()::text)") if is_pg else None,
            ),
        )
        batch_op.create_unique_constraint("user_fs_uniquifier_key", ["fs_uniquifier"])


def downgrade():
    with op.batch_alter_table("user") as batch_op:
        batch_op.drop_constraint("user_fs_uniquifier_key", type_="unique")
        batch_op.drop_column("fs_uniquifier")
