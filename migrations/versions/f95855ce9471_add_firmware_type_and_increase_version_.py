"""Add firmware type and increase version length

Revision ID: f95855ce9471
Revises: 76d559b4e873
Create Date: 2024-01-15 13:58:34.160242

"""

import sqlalchemy as sa
from alembic import op

revision = "f95855ce9471"
down_revision = "76d559b4e873"


def upgrade():
    op.add_column("firmware", sa.Column("type", sa.Unicode(length=4)))
    # Set type based on version
    op.execute(
        """
        UPDATE firmware
        SET type = CASE
            WHEN version LIKE '1.%' THEN 'srm'
            ELSE 'dsm'
        END
    """
    )
    # Modify the column to be NOT NULL after setting the values
    op.alter_column("firmware", "type", nullable=False)

    op.alter_column(
        "firmware",
        "version",
        existing_type=sa.VARCHAR(length=3),
        type_=sa.Unicode(length=4),
        existing_nullable=False,
    )


def downgrade():
    op.alter_column(
        "firmware",
        "version",
        existing_type=sa.Unicode(length=4),
        type_=sa.VARCHAR(length=3),
        existing_nullable=False,
    )
    op.drop_column("firmware", "type")
