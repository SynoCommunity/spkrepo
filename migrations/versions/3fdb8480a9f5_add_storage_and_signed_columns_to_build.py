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
            "CREATE TYPE IF NOT EXISTS storage_location AS ENUM ('local', 'remote')"
        )
    op.add_column(
        "build",
        sa.Column(
            "storage",
            sa.Enum("local", "remote", name="storage_location", create_type=not is_pg),
            nullable=False,
            server_default="local",
        ),
    )
    op.add_column(
        "build",
        sa.Column("signed", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("build", "signed")
    op.drop_column("build", "storage")
    if op.get_bind().engine.dialect.name == "postgresql":
        op.execute("DROP TYPE IF EXISTS storage_location")
