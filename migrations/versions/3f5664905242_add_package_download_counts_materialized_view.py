"""add package_download_counts materialized view, firmware/architecture indexes

Revision ID: 3f5664905242
Revises: 1fa3599ed198
Create Date: 2026-06-20 14:00:00.000000

Changes
-------
1. package_download_counts materialized view
   Replaces ~7000 correlated per-row subqueries against download_stat that
   were firing on every catalog cache miss. The view is refreshed hourly by
   the refresh_download_counts Celery task.

2. ix_firmware_version (text_pattern_ops)
   Supports the LIKE '7.%' / startswith() filter on firmware.version.
   text_pattern_ops is required because the DB collation is en_US.utf8
   (not C/POSIX), which prevents standard btree indexes from being used
   for prefix LIKE patterns.

3. ix_firmware_build_version (text_pattern_ops on version column)
   Composite index covering the combined build range + version prefix
   filter used in both catalog subqueries.

4. ix_architecture_id_code
   Composite index covering the join on architecture.id plus the equality
   filter on architecture.code, which was driving thousands of extra scans.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "3f5664905242"
down_revision: Union[str, Sequence[str], None] = "1fa3599ed198"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    is_pg = op.get_bind().engine.dialect.name == "postgresql"

    # 1. Materialized view for package download counts
    if is_pg:
        op.execute(
            """
            CREATE MATERIALIZED VIEW package_download_counts AS
            SELECT
                package_id,
                COALESCE(SUM(count), 0) AS download_count,
                COALESCE(
                    SUM(count) FILTER (WHERE date >= CURRENT_DATE - 90), 0
                ) AS recent_download_count
            FROM download_stat
            GROUP BY package_id
            WITH DATA
            """
        )
        op.execute(
            "CREATE UNIQUE INDEX ix_package_download_counts_package_id "
            "ON package_download_counts (package_id)"
        )

    # 2. firmware.version index with text_pattern_ops
    #    (required for LIKE '7.%' with en_US.utf8 collation)
    op.create_index(
        "ix_firmware_version",
        "firmware",
        ["version"],
        postgresql_ops={"version": "text_pattern_ops"},
    )

    # 3. Composite firmware index covering build range + version prefix
    op.create_index(
        "ix_firmware_build_version",
        "firmware",
        ["build", "version"],
        postgresql_ops={"version": "text_pattern_ops"},
    )

    # 4. Composite architecture index covering join + code filter
    op.create_index(
        "ix_architecture_id_code",
        "architecture",
        ["id", "code"],
    )


def downgrade() -> None:
    is_pg = op.get_bind().engine.dialect.name == "postgresql"

    op.drop_index("ix_architecture_id_code", table_name="architecture")
    op.drop_index("ix_firmware_build_version", table_name="firmware")
    op.drop_index("ix_firmware_version", table_name="firmware")
    if is_pg:
        op.execute("DROP MATERIALIZED VIEW IF EXISTS package_download_counts")
