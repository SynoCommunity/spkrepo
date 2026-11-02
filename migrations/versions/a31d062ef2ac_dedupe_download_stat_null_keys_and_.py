"""dedupe download_stat NULL keys and enforce NULLS NOT DISTINCT

Revision ID: a31d062ef2ac
Revises: 3f5664905242
Create Date: 2026-11-02 09:22:40.325960

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a31d062ef2ac"
down_revision: Union[str, Sequence[str], None] = "3f5664905242"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Fold each duplicate group into its lowest id, summing the counts.
_MERGE_TOTALS = """
WITH dup AS (
    SELECT package_id, architecture_id, firmware_build,
           target_firmware_build, date,
           min(id) AS keep_id, sum(count) AS total
    FROM download_stat
    GROUP BY package_id, architecture_id, firmware_build,
             target_firmware_build, date
    HAVING count(*) > 1
)
UPDATE download_stat ds
SET count = dup.total
FROM dup
WHERE ds.id = dup.keep_id
"""

# Remove the non-keep rows (IS NOT DISTINCT FROM matches NULLs).
_DELETE_DUPLICATES = """
DELETE FROM download_stat ds
USING (
    SELECT package_id, architecture_id, firmware_build,
           target_firmware_build, date, min(id) AS keep_id
    FROM download_stat
    GROUP BY package_id, architecture_id, firmware_build,
             target_firmware_build, date
    HAVING count(*) > 1
) dup
WHERE ds.package_id IS NOT DISTINCT FROM dup.package_id
  AND ds.architecture_id IS NOT DISTINCT FROM dup.architecture_id
  AND ds.firmware_build IS NOT DISTINCT FROM dup.firmware_build
  AND ds.target_firmware_build IS NOT DISTINCT FROM dup.target_firmware_build
  AND ds.date = dup.date
  AND ds.id <> dup.keep_id
"""


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    """Merge NULL-distinct rows and enforce NULLS NOT DISTINCT (Postgres only).

    Postgres treats NULLs as distinct in unique constraints, so manual
    downloads (NULL device dimensions) were re-inserted by every ingest
    instead of updating. This folds each duplicate group into its lowest id,
    then makes the constraint NULLS NOT DISTINCT so the upsert updates those
    rows. Sums are preserved, so the materialized view needs no refresh.

    SQLite cannot express NULLS NOT DISTINCT, so it is left unchanged.
    """
    if not _is_postgres():
        return

    op.execute(_MERGE_TOTALS)
    op.execute(_DELETE_DUPLICATES)

    op.execute("ALTER TABLE download_stat DROP CONSTRAINT uq_download_stat")
    op.execute(
        "ALTER TABLE download_stat ADD CONSTRAINT uq_download_stat "
        "UNIQUE NULLS NOT DISTINCT (package_id, architecture_id, "
        "firmware_build, target_firmware_build, date)"
    )

    # Redundant with ix_download_stat_package_id_date (leading package_id).
    op.execute("DROP INDEX IF EXISTS ix_download_stat_package_id")


def downgrade() -> None:
    """Restore the NULLS DISTINCT constraint and standalone index.

    The merge cannot be reversed: duplicate rows are deleted, not archived.
    """
    if not _is_postgres():
        return

    op.create_index(
        "ix_download_stat_package_id",
        "download_stat",
        ["package_id"],
        unique=False,
    )
    op.execute("ALTER TABLE download_stat DROP CONSTRAINT uq_download_stat")
    op.execute(
        "ALTER TABLE download_stat ADD CONSTRAINT uq_download_stat "
        "UNIQUE (package_id, architecture_id, firmware_build, "
        "target_firmware_build, date)"
    )
