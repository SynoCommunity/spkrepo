"""Create database

Revision ID: 26b4c36c11e
Revises: None
Create Date: 2014-12-03 00:14:38.427893

"""

import sqlalchemy as sa
from alembic import op

revision = "26b4c36c11e"
down_revision = None


def upgrade():
    op.create_table(
        "user",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("username", sa.Unicode(length=50), nullable=False),
        sa.Column("email", sa.Unicode(length=254), nullable=False),
        sa.Column("password", sa.Unicode(length=255), nullable=False),
        sa.Column("api_key", sa.Unicode(length=64), nullable=True),
        sa.Column("github_access_token", sa.Unicode(length=255), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("api_key"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("username"),
    )
    role_table = op.create_table(
        "role",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Unicode(length=50), nullable=False),
        sa.Column("description", sa.Unicode(length=255), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.bulk_insert(
        role_table,
        [
            {"name": "admin", "description": "Administrator"},
            {"name": "package_admin", "description": "Package Administrator"},
            {"name": "developer", "description": "Developer"},
        ],
    )
    architecture_table = op.create_table(
        "architecture",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Unicode(length=20), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.bulk_insert(
        architecture_table,
        [
            {"code": "noarch"},
            {"code": "ppc824x"},
            {"code": "ppc854x"},
            {"code": "ppc853x"},
            {"code": "88f628x"},
            {"code": "x86"},
            {"code": "bromolow"},
            {"code": "cedarview"},
            {"code": "qoriq"},
            {"code": "armada370"},
            {"code": "armadaxp"},
            {"code": "evansport"},
            {"code": "comcerto2k"},
            {"code": "avoton"},
            {"code": "armada375"},
        ],
    )
    language_table = op.create_table(
        "language",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Unicode(length=3), nullable=False),
        sa.Column("name", sa.Unicode(length=50), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.bulk_insert(
        language_table,
        [
            {"code": "enu", "name": "English"},
            {"code": "cht", "name": "Traditional Chinese"},
            {"code": "chs", "name": "Simplified Chinese"},
            {"code": "krn", "name": "Korean"},
            {"code": "ger", "name": "German"},
            {"code": "fre", "name": "French"},
            {"code": "ita", "name": "Italian"},
            {"code": "spn", "name": "Spanish"},
            {"code": "jpn", "name": "Japanese"},
            {"code": "dan", "name": "Danish"},
            {"code": "nor", "name": "Norwegian"},
            {"code": "sve", "name": "Swedish"},
            {"code": "nld", "name": "Dutch"},
            {"code": "rus", "name": "Russian"},
            {"code": "plk", "name": "Polish"},
            {"code": "ptb", "name": "Brazilian Portuguese"},
            {"code": "ptg", "name": "European Portuguese"},
            {"code": "hun", "name": "Hungarian"},
            {"code": "trk", "name": "Turkish"},
            {"code": "csy", "name": "Czech"},
        ],
    )
    firmware_table = op.create_table(
        "firmware",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Unicode(length=3), nullable=False),
        sa.Column("build", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("build"),
    )
    op.bulk_insert(
        firmware_table,
        [
            {"version": "2.0", "build": 731},
            {"version": "2.1", "build": 844},
            {"version": "2.2", "build": 942},
            {"version": "2.3", "build": 1139},
            {"version": "3.0", "build": 1337},
            {"version": "3.1", "build": 1594},
            {"version": "3.2", "build": 1922},
            {"version": "4.0", "build": 2198},
            {"version": "4.1", "build": 2636},
            {"version": "4.2", "build": 3202},
            {"version": "4.3", "build": 3776},
            {"version": "5.0", "build": 4458},
            {"version": "5.1", "build": 5004},
        ],
    )
    service_table = op.create_table(
        "service",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("code", sa.Unicode(length=30), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("code"),
    )
    op.bulk_insert(
        service_table,
        [
            {"code": "apache-web"},
            {"code": "mysql"},
            {"code": "php_disable_safe_exec_dir"},
            {"code": "ssh"},
        ],
    )
    op.create_table(
        "package",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("author_user_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.Unicode(length=50), nullable=False),
        sa.Column("insert_date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["author_user_id"], ["user.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.create_table(
        "user_role",
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("role_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["role_id"],
            ["role.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
    )
    op.create_table(
        "screenshot",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("path", sa.Unicode(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["package.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "version",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("package_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("upstream_version", sa.Unicode(length=20), nullable=False),
        sa.Column("changelog", sa.UnicodeText(), nullable=True),
        sa.Column("report_url", sa.Unicode(length=255), nullable=True),
        sa.Column("distributor", sa.Unicode(length=50), nullable=True),
        sa.Column("distributor_url", sa.Unicode(length=255), nullable=True),
        sa.Column("maintainer", sa.Unicode(length=50), nullable=True),
        sa.Column("maintainer_url", sa.Unicode(length=255), nullable=True),
        sa.Column("dependencies", sa.Unicode(length=255), nullable=True),
        sa.Column("conf_dependencies", sa.Unicode(length=255), nullable=True),
        sa.Column("conflicts", sa.Unicode(length=255), nullable=True),
        sa.Column("conf_conflicts", sa.Unicode(length=255), nullable=True),
        sa.Column("install_wizard", sa.Boolean(), nullable=True),
        sa.Column("upgrade_wizard", sa.Boolean(), nullable=True),
        sa.Column("startable", sa.Boolean(), nullable=True),
        sa.Column("license", sa.UnicodeText(), nullable=True),
        sa.Column("insert_date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["package.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("package_id", "version"),
    )
    with op.batch_alter_table("version", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_version_version"), ["version"], unique=False
        )

    op.create_table(
        "package_user_maintainer",
        sa.Column("package_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["package_id"],
            ["package.id"],
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["user.id"],
        ),
    )
    op.create_table(
        "version_service_dependency",
        sa.Column("version_id", sa.Integer(), nullable=True),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["service_id"],
            ["service.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["version.id"],
        ),
    )
    op.create_table(
        "build",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("firmware_id", sa.Integer(), nullable=False),
        sa.Column("publisher_user_id", sa.Integer(), nullable=True),
        sa.Column("checksum", sa.Unicode(length=32), nullable=True),
        sa.Column("extract_size", sa.Integer(), nullable=True),
        sa.Column("path", sa.Unicode(length=100), nullable=True),
        sa.Column("md5", sa.Unicode(length=32), nullable=True),
        sa.Column("insert_date", sa.DateTime(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ["firmware_id"],
            ["firmware.id"],
        ),
        sa.ForeignKeyConstraint(
            ["publisher_user_id"],
            ["user.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["version.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "icon",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column(
            "size", sa.Enum("72", "120", "256", name="icon_size"), nullable=False
        ),
        sa.Column("path", sa.Unicode(length=100), nullable=False),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["version.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version_id", "size"),
    )
    op.create_table(
        "description",
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("language_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.UnicodeText(), nullable=False),
        sa.ForeignKeyConstraint(
            ["language_id"],
            ["language.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["version.id"],
        ),
        sa.PrimaryKeyConstraint("version_id", "language_id"),
    )
    op.create_table(
        "displayname",
        sa.Column("version_id", sa.Integer(), nullable=False),
        sa.Column("language_id", sa.Integer(), nullable=False),
        sa.Column("displayname", sa.Unicode(length=50), nullable=False),
        sa.ForeignKeyConstraint(
            ["language_id"],
            ["language.id"],
        ),
        sa.ForeignKeyConstraint(
            ["version_id"],
            ["version.id"],
        ),
        sa.PrimaryKeyConstraint("version_id", "language_id"),
    )
    op.create_table(
        "build_architecture",
        sa.Column("build_id", sa.Integer(), nullable=True),
        sa.Column("architecture_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["architecture_id"],
            ["architecture.id"],
        ),
        sa.ForeignKeyConstraint(
            ["build_id"],
            ["build.id"],
        ),
    )
    op.create_table(
        "download",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("build_id", sa.Integer(), nullable=False),
        sa.Column("architecture_id", sa.Integer(), nullable=False),
        sa.Column("firmware_build", sa.Integer(), nullable=False),
        sa.Column("ip_address", sa.Unicode(length=46), nullable=False),
        sa.Column("user_agent", sa.Unicode(length=255), nullable=True),
        sa.Column("date", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["architecture_id"],
            ["architecture.id"],
        ),
        sa.ForeignKeyConstraint(
            ["build_id"],
            ["build.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade():
    op.drop_table("download")
    op.drop_table("build_architecture")
    op.drop_table("displayname")
    op.drop_table("description")
    op.drop_table("icon")
    sa.Enum(name="icon_size").drop(op.get_bind(), checkfirst=False)
    op.drop_table("build")
    op.drop_table("version_service_dependency")
    op.drop_table("package_user_maintainer")
    with op.batch_alter_table("version", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_version_version"))
    op.drop_table("version")
    op.drop_table("screenshot")
    op.drop_table("user_role")
    op.drop_table("package")
    op.drop_table("service")
    op.drop_table("firmware")
    op.drop_table("language")
    op.drop_table("architecture")
    op.drop_table("role")
    op.drop_table("user")
