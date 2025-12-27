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
    op.add_column(
        "user",
        sa.Column(
            "fs_uniquifier",
            sa.String(length=255),
            nullable=False,
            server_default=sa.text("md5(random()::text)"),
        ),
    )
    op.create_unique_constraint("user_fs_uniquifier_key", "user", ["fs_uniquifier"])


def downgrade():
    op.drop_constraint("user_fs_uniquifier_key", "user", type_="unique")
    op.drop_column("user", "fs_uniquifier")
