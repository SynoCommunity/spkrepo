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
    op.add_column(
        "download_stat",
        sa.Column(
            "download_source",
            sa.Enum("catalog", "manual", name="download_source"),
            server_default="catalog",
            nullable=False,
        ),
    )
    op.alter_column(
        "download_stat", "architecture_id", existing_type=sa.INTEGER(), nullable=True
    )
    op.alter_column(
        "download_stat", "firmware_build", existing_type=sa.INTEGER(), nullable=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "download_stat", "firmware_build", existing_type=sa.INTEGER(), nullable=False
    )
    op.alter_column(
        "download_stat", "architecture_id", existing_type=sa.INTEGER(), nullable=False
    )
    op.drop_column("download_stat", "download_source")
