"""Increase field sizes

Revision ID: dc7687894ba7
Revises: d785f1fb2307
Create Date: 2021-09-19 22:47:15.128884

"""

import sqlalchemy as sa
from alembic import op

revision = "dc7687894ba7"
down_revision = "d785f1fb2307"


def upgrade():
    op.alter_column(
        "version",
        "conf_dependencies",
        existing_type=sa.VARCHAR(length=255),
        type_=sa.UnicodeText(),
        existing_nullable=True,
    )
    op.alter_column(
        "version",
        "conf_conflicts",
        existing_type=sa.VARCHAR(length=255),
        type_=sa.UnicodeText(),
        existing_nullable=True,
    )
    op.alter_column(
        "version",
        "conf_privilege",
        existing_type=sa.VARCHAR(length=255),
        type_=sa.UnicodeText(),
        existing_nullable=True,
    )
    op.alter_column(
        "version",
        "conf_resource",
        existing_type=sa.VARCHAR(length=255),
        type_=sa.UnicodeText(),
        existing_nullable=True,
    )


def downgrade():
    op.alter_column(
        "version",
        "conf_resource",
        existing_type=sa.UnicodeText(),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "version",
        "conf_privilege",
        existing_type=sa.UnicodeText(),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "version",
        "conf_conflicts",
        existing_type=sa.UnicodeText(),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )
    op.alter_column(
        "version",
        "conf_dependencies",
        existing_type=sa.UnicodeText(),
        type_=sa.VARCHAR(length=255),
        existing_nullable=True,
    )
