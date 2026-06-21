"""add target firmware tracking to download stats

Revision ID: 325d7d86f788
Revises: 3fdb8480a9f5
Create Date: 2026-06-14 10:43:33.209412

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "325d7d86f788"
down_revision: Union[str, Sequence[str], None] = "3fdb8480a9f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("download_stat") as batch_op:
        batch_op.add_column(sa.Column("target_firmware_build", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "target_noarch",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("false"),
            ),
        )
        batch_op.drop_constraint(op.f("uq_download_stat"), type_="unique")
        batch_op.create_unique_constraint(
            "uq_download_stat",
            [
                "package_id",
                "architecture_id",
                "firmware_build",
                "target_firmware_build",
                "date",
            ],
        )
    op.create_index(
        op.f("ix_download_stat_target_firmware_build"),
        "download_stat",
        ["target_firmware_build"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_download_stat_target_firmware_build"), table_name="download_stat"
    )
    with op.batch_alter_table("download_stat") as batch_op:
        batch_op.drop_constraint("uq_download_stat", type_="unique")
        batch_op.create_unique_constraint(
            op.f("uq_download_stat"),
            ["package_id", "architecture_id", "firmware_build", "date"],
        )
        batch_op.drop_column("target_noarch")
        batch_op.drop_column("target_firmware_build")
