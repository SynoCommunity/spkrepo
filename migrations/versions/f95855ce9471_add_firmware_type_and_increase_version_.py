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
    with op.batch_alter_table("firmware") as batch_op:
        batch_op.add_column(sa.Column("type", sa.Unicode(length=4)))
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
    with op.batch_alter_table("firmware") as batch_op:
        batch_op.alter_column("type", nullable=False)
        batch_op.alter_column(
            "version",
            existing_type=sa.VARCHAR(length=3),
            type_=sa.Unicode(length=4),
            existing_nullable=False,
        )


def downgrade():
    with op.batch_alter_table("firmware") as batch_op:
        batch_op.alter_column(
            "version",
            existing_type=sa.Unicode(length=4),
            type_=sa.VARCHAR(length=3),
            existing_nullable=False,
        )
        batch_op.drop_column("type")
