"""Move changelog and description from version to build

Revision ID: c63ff65c708a
Revises: 23bbd5c74cd0
Create Date: 2026-06-09 00:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c63ff65c708a"
down_revision: Union[str, Sequence[str], None] = "23bbd5c74cd0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("build") as batch_op:
        batch_op.add_column(sa.Column("changelog", sa.UnicodeText(), nullable=True))

    op.create_table(
        "build_description",
        sa.Column("build_id", sa.Integer(), nullable=False),
        sa.Column("language_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.UnicodeText(), nullable=False),
        sa.ForeignKeyConstraint(["build_id"], ["build.id"]),
        sa.ForeignKeyConstraint(["language_id"], ["language.id"]),
        sa.PrimaryKeyConstraint("build_id", "language_id"),
    )

    op.execute(
        """
        UPDATE build
        SET changelog = (
            SELECT changelog FROM version WHERE version.id = build.version_id
        )
        """
    )

    op.execute(
        """
        INSERT INTO build_description (build_id, language_id, description)
        SELECT b.id, d.language_id, d.description
        FROM build b
        JOIN description d ON d.version_id = b.version_id
        """
    )

    with op.batch_alter_table("version") as batch_op:
        batch_op.drop_column("changelog")

    op.drop_table("description")


def downgrade() -> None:
    op.create_table(
        "description",
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("language_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.UnicodeText(), nullable=False),
        sa.ForeignKeyConstraint(["version_id"], ["version.id"]),
        sa.ForeignKeyConstraint(["language_id"], ["language.id"]),
        sa.PrimaryKeyConstraint("version_id", "language_id"),
    )

    op.execute(
        """
        INSERT INTO description (version_id, language_id, description)
        SELECT b.version_id, bd.language_id, MIN(bd.description) AS description
        FROM build_description bd
        JOIN build b ON b.id = bd.build_id
        GROUP BY b.version_id, bd.language_id
        """
    )

    op.drop_table("build_description")

    with op.batch_alter_table("version") as batch_op:
        batch_op.add_column(sa.Column("changelog", sa.UnicodeText(), nullable=True))

    op.execute(
        """
        UPDATE version
        SET changelog = (
            SELECT changelog FROM build
            WHERE build.version_id = version.id AND changelog IS NOT NULL
            LIMIT 1
        )
        """
    )

    with op.batch_alter_table("build") as batch_op:
        batch_op.drop_column("changelog")
