"""add storage and signed columns to build

Revision ID: 3fdb8480a9f5
Revises: c63ff65c708a
Create Date: 2026-06-10 22:12:49.873842

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3fdb8480a9f5"
down_revision: Union[str, Sequence[str], None] = "c63ff65c708a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    is_pg = op.get_bind().engine.dialect.name == "postgresql"
    if is_pg:
        op.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'storage_location') THEN CREATE TYPE storage_location AS ENUM ('local', 'remote'); END IF; END $$"
        )
    with op.batch_alter_table("build") as batch_op:
        batch_op.add_column(
            sa.Column(
                "storage",
                sa.Enum(
                    "local", "remote", name="storage_location", create_type=not is_pg
                ),
                nullable=False,
                server_default="local",
            ),
        )
        batch_op.add_column(
            sa.Column("signed", sa.Boolean(), nullable=False, server_default="false"),
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("build") as batch_op:
        batch_op.drop_column("signed")
        batch_op.drop_column("storage")
    if op.get_bind().engine.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS storage_location")
