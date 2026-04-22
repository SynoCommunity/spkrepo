"""Remove unused extract_size column and add size column to build table

Revision ID: 05cba02585a2
Revises: 30bc0c0455f8
Create Date: 2026-04-22 04:21:22.505628

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "05cba02585a2"
down_revision: Union[str, Sequence[str], None] = "30bc0c0455f8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("build", sa.Column("size", sa.Integer(), nullable=True))
    op.drop_column("build", "extract_size")


def downgrade() -> None:
    """Downgrade schema."""
    op.add_column(
        "build",
        sa.Column("extract_size", sa.INTEGER(), autoincrement=False, nullable=True),
    )
    op.drop_column("build", "size")
