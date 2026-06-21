"""add download_source enum, make arch_id and fw_build nullable

Revision ID: 1fa3599ed198
Revises: 325d7d86f788
Create Date: 2026-06-16 05:34:26.729294

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1fa3599ed198"
down_revision: Union[str, Sequence[str], None] = "325d7d86f788"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    is_pg = op.get_bind().engine.dialect.name == "postgresql"
    if is_pg:
        op.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'download_source') THEN CREATE TYPE download_source AS ENUM ('catalog', 'manual'); END IF; END $$"
        )
    with op.batch_alter_table("download_stat") as batch_op:
        batch_op.add_column(
            sa.Column(
                "download_source",
                sa.Enum(
                    "catalog", "manual", name="download_source", create_type=not is_pg
                ),
                server_default="catalog",
                nullable=False,
            ),
        )
        batch_op.alter_column(
            "architecture_id", existing_type=sa.INTEGER(), nullable=True
        )
        batch_op.alter_column(
            "firmware_build", existing_type=sa.INTEGER(), nullable=True
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("download_stat") as batch_op:
        batch_op.alter_column(
            "firmware_build", existing_type=sa.INTEGER(), nullable=False
        )
        batch_op.alter_column(
            "architecture_id", existing_type=sa.INTEGER(), nullable=False
        )
        batch_op.drop_column("download_source")
    if op.get_bind().engine.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS download_source")
