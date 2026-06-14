"""Replace download with download_stat

Revision ID: 23bbd5c74cd0
Revises: 02a2b583dfae
Create Date: 2026-06-03 23:26:45.582364

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "23bbd5c74cd0"
down_revision: Union[str, Sequence[str], None] = "02a2b583dfae"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "download_stat",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("build_id", sa.Integer(), nullable=True),
        sa.Column("architecture_id", sa.Integer(), nullable=False),
        sa.Column("firmware_build", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["architecture_id"],
            ["architecture.id"],
        ),
        sa.ForeignKeyConstraint(["build_id"], ["build.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["package.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "package_id",
            "architecture_id",
            "firmware_build",
            "date",
            name="uq_download_stat",
        ),
    )
    op.create_index(
        op.f("ix_download_stat_architecture_id"),
        "download_stat",
        ["architecture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_download_stat_build_id"), "download_stat", ["build_id"], unique=False
    )
    op.create_index(
        op.f("ix_download_stat_date"), "download_stat", ["date"], unique=False
    )
    op.create_index(
        op.f("ix_download_stat_firmware_build"),
        "download_stat",
        ["firmware_build"],
        unique=False,
    )
    op.create_index(
        op.f("ix_download_stat_package_id"),
        "download_stat",
        ["package_id"],
        unique=False,
    )
    op.create_index(
        "ix_download_stat_package_id_date",
        "download_stat",
        ["package_id", "date"],
        unique=False,
    )
    op.drop_index(op.f("ix_download_architecture_id"), table_name="download")
    op.drop_index(op.f("ix_download_build_id"), table_name="download")
    op.drop_index(op.f("ix_download_date"), table_name="download")
    op.drop_table("download")
    op.create_index(
        op.f("ix_version_package_id"), "version", ["package_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema.

    Note: the restored 'download' table is structurally correct but the
    corresponding Download model and nas.download route no longer exist
    in the codebase. Downgrading will restore the schema but the application
    will not function correctly without reverting the associated code changes.
    """
    op.drop_index(op.f("ix_version_package_id"), table_name="version")
    op.create_table(
        "download",
        sa.Column("id", sa.INTEGER(), autoincrement=True, nullable=False),
        sa.Column("build_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("architecture_id", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("firmware_build", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column(
            "ip_address", sa.VARCHAR(length=46), autoincrement=False, nullable=False
        ),
        sa.Column(
            "user_agent", sa.VARCHAR(length=255), autoincrement=False, nullable=True
        ),
        sa.Column("date", sa.DateTime(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["architecture_id"],
            ["architecture.id"],
            name=op.f("download_architecture_id_fkey"),
        ),
        sa.ForeignKeyConstraint(
            ["build_id"], ["build.id"], name=op.f("download_build_id_fkey")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("download_pkey")),
    )
    op.create_index(op.f("ix_download_date"), "download", ["date"], unique=False)
    op.create_index(
        op.f("ix_download_build_id"), "download", ["build_id"], unique=False
    )
    op.create_index(
        op.f("ix_download_architecture_id"),
        "download",
        ["architecture_id"],
        unique=False,
    )
    op.drop_index("ix_download_stat_package_id_date", table_name="download_stat")
    op.drop_index(op.f("ix_download_stat_package_id"), table_name="download_stat")
    op.drop_index(op.f("ix_download_stat_firmware_build"), table_name="download_stat")
    op.drop_index(op.f("ix_download_stat_date"), table_name="download_stat")
    op.drop_index(op.f("ix_download_stat_build_id"), table_name="download_stat")
    op.drop_index(op.f("ix_download_stat_architecture_id"), table_name="download_stat")
    op.drop_table("download_stat")
