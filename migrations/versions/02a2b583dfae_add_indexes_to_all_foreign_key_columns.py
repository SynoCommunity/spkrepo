"""Add indexes to all foreign key columns

Revision ID: 02a2b583dfae
Revises: 05cba02585a2
Create Date: 2026-06-02 14:53:06.012620

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "02a2b583dfae"
down_revision: Union[str, Sequence[str], None] = "05cba02585a2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        "idx_build_version_active", "build", ["version_id", "active"], unique=False
    )
    op.create_index(
        op.f("ix_build_firmware_max_id"), "build", ["firmware_max_id"], unique=False
    )
    op.create_index(
        op.f("ix_build_firmware_min_id"), "build", ["firmware_min_id"], unique=False
    )
    op.create_index(
        op.f("ix_build_publisher_user_id"), "build", ["publisher_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_build_architecture_architecture_id"),
        "build_architecture",
        ["architecture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_build_architecture_build_id"),
        "build_architecture",
        ["build_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_download_architecture_id"),
        "download",
        ["architecture_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_download_build_id"), "download", ["build_id"], unique=False
    )
    op.create_index(op.f("ix_download_date"), "download", ["date"], unique=False)
    op.create_index(
        op.f("ix_package_author_user_id"), "package", ["author_user_id"], unique=False
    )
    op.create_index(
        op.f("ix_package_user_maintainer_package_id"),
        "package_user_maintainer",
        ["package_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_package_user_maintainer_user_id"),
        "package_user_maintainer",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_screenshot_package_id"), "screenshot", ["package_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_role_role_id"), "user_role", ["role_id"], unique=False
    )
    op.create_index(
        op.f("ix_user_role_user_id"), "user_role", ["user_id"], unique=False
    )
    op.create_index(
        op.f("ix_version_service_dependency_service_id"),
        "version_service_dependency",
        ["service_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_version_service_dependency_version_id"),
        "version_service_dependency",
        ["version_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_version_service_dependency_version_id"),
        table_name="version_service_dependency",
    )
    op.drop_index(
        op.f("ix_version_service_dependency_service_id"),
        table_name="version_service_dependency",
    )
    op.drop_index(op.f("ix_user_role_user_id"), table_name="user_role")
    op.drop_index(op.f("ix_user_role_role_id"), table_name="user_role")
    op.drop_index(op.f("ix_screenshot_package_id"), table_name="screenshot")
    op.drop_index(
        op.f("ix_package_user_maintainer_user_id"), table_name="package_user_maintainer"
    )
    op.drop_index(
        op.f("ix_package_user_maintainer_package_id"),
        table_name="package_user_maintainer",
    )
    op.drop_index(op.f("ix_package_author_user_id"), table_name="package")
    op.drop_index(op.f("ix_download_date"), table_name="download")
    op.drop_index(op.f("ix_download_build_id"), table_name="download")
    op.drop_index(op.f("ix_download_architecture_id"), table_name="download")
    op.drop_index(
        op.f("ix_build_architecture_build_id"), table_name="build_architecture"
    )
    op.drop_index(
        op.f("ix_build_architecture_architecture_id"), table_name="build_architecture"
    )
    op.drop_index(op.f("ix_build_publisher_user_id"), table_name="build")
    op.drop_index(op.f("ix_build_firmware_min_id"), table_name="build")
    op.drop_index(op.f("ix_build_firmware_max_id"), table_name="build")
    op.drop_index("idx_build_version_active", table_name="build")
