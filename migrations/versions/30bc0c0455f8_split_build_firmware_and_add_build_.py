"""Split Build Firmware and add Build Manifest

Revision ID: 30bc0c0455f8
Revises: f95855ce9471
Create Date: 2025-11-05 20:43:32.593098

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "30bc0c0455f8"
down_revision = "f95855ce9471"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    meta = sa.MetaData()

    # 1) Add new columns (nullable for backfill), add FKs
    op.add_column("build", sa.Column("firmware_min_id", sa.Integer(), nullable=True))
    op.add_column("build", sa.Column("firmware_max_id", sa.Integer(), nullable=True))
    op.create_foreign_key(None, "build", "firmware", ["firmware_min_id"], ["id"])
    op.create_foreign_key(None, "build", "firmware", ["firmware_max_id"], ["id"])

    # 2) Backfill firmware_min_id from legacy firmware_id (still present right now)
    op.execute("UPDATE build SET firmware_min_id = firmware_id")

    # 3) Make firmware_min_id NOT NULL
    op.alter_column(
        "build", "firmware_min_id", existing_type=sa.Integer(), nullable=False
    )

    # 4) Drop old FK and legacy column firmware_id
    op.drop_constraint(op.f("build_firmware_id_fkey"), "build", type_="foreignkey")
    op.drop_column("build", "firmware_id")

    # 5) Create buildmanifest table
    op.create_table(
        "buildmanifest",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("build_id", sa.Integer(), nullable=False, unique=True),
        sa.Column("dependencies", sa.Unicode(255)),
        sa.Column("conf_dependencies", sa.UnicodeText()),
        sa.Column("conflicts", sa.Unicode(255)),
        sa.Column("conf_conflicts", sa.UnicodeText()),
        sa.Column("conf_privilege", sa.UnicodeText()),
        sa.Column("conf_resource", sa.UnicodeText()),
        sa.ForeignKeyConstraint(["build_id"], ["build.id"]),
    )

    # 6) Reflect
    build = sa.Table("build", meta, autoload_with=bind)
    version = sa.Table("version", meta, autoload_with=bind)
    buildmanifest = sa.Table("buildmanifest", meta, autoload_with=bind)

    # 7) Backfill buildmanifest: one row per build using its version’s fields
    sel = sa.select(
        build.c.id.label("build_id"),
        version.c.dependencies,
        version.c.conf_dependencies,
        version.c.conflicts,
        version.c.conf_conflicts,
        version.c.conf_privilege,
        version.c.conf_resource,
    ).select_from(build.join(version, build.c.version_id == version.c.id))

    rows = bind.execute(sel).fetchall()
    if rows:
        bind.execute(
            buildmanifest.insert(),
            [
                {
                    "build_id": r.build_id,
                    "dependencies": r.dependencies,
                    "conf_dependencies": r.conf_dependencies,
                    "conflicts": r.conflicts,
                    "conf_conflicts": r.conf_conflicts,
                    "conf_privilege": r.conf_privilege,
                    "conf_resource": r.conf_resource,
                }
                for r in rows
            ],
        )

    # 8) Drop moved columns from version
    op.drop_column("version", "conf_resource")
    op.drop_column("version", "conf_dependencies")
    op.drop_column("version", "conf_conflicts")
    op.drop_column("version", "dependencies")
    op.drop_column("version", "conf_privilege")
    op.drop_column("version", "conflicts")


def downgrade():
    bind = op.get_bind()
    meta = sa.MetaData()

    # 1) Recreate columns on version
    op.add_column("version", sa.Column("conflicts", sa.Unicode(255)))
    op.add_column("version", sa.Column("conf_privilege", sa.UnicodeText()))
    op.add_column("version", sa.Column("dependencies", sa.Unicode(255)))
    op.add_column("version", sa.Column("conf_conflicts", sa.UnicodeText()))
    op.add_column("version", sa.Column("conf_dependencies", sa.UnicodeText()))
    op.add_column("version", sa.Column("conf_resource", sa.UnicodeText()))

    # Reflect
    version = sa.Table("version", meta, autoload_with=bind)
    build = sa.Table("build", meta, autoload_with=bind)
    buildmanifest = sa.Table("buildmanifest", meta, autoload_with=bind)

    # 2) Copy manifest back to version using the first build (lowest build.id) per version
    first_build_cte = (
        sa.select(
            build.c.version_id,
            sa.func.min(build.c.id).label("first_build_id"),
        )
        .group_by(build.c.version_id)
        .cte("first_build")
    )

    sel = sa.select(
        version.c.id.label("version_id"),
        buildmanifest.c.dependencies,
        buildmanifest.c.conf_dependencies,
        buildmanifest.c.conflicts,
        buildmanifest.c.conf_conflicts,
        buildmanifest.c.conf_privilege,
        buildmanifest.c.conf_resource,
    ).select_from(
        version.join(first_build_cte, first_build_cte.c.version_id == version.c.id)
        .join(build, build.c.id == first_build_cte.c.first_build_id)
        .join(buildmanifest, buildmanifest.c.build_id == build.c.id)
    )

    rows = bind.execute(sel).fetchall()
    for r in rows:
        bind.execute(
            version.update()
            .where(version.c.id == r.version_id)
            .values(
                dependencies=r.dependencies,
                conf_dependencies=r.conf_dependencies,
                conflicts=r.conflicts,
                conf_conflicts=r.conf_conflicts,
                conf_privilege=r.conf_privilege,
                conf_resource=r.conf_resource,
            )
        )

    # 3) Drop buildmanifest
    op.drop_table("buildmanifest")

    # 4) Restore legacy firmware_id and backfill from firmware_min_id
    op.add_column("build", sa.Column("firmware_id", sa.Integer(), nullable=True))

    op.execute("UPDATE build SET firmware_id = firmware_min_id")

    op.alter_column("build", "firmware_id", existing_type=sa.Integer(), nullable=False)
    op.create_foreign_key(
        op.f("build_firmware_id_fkey"), "build", "firmware", ["firmware_id"], ["id"]
    )

    # 5) Drop FKs on firmware_min_id / firmware_max_id (names may be auto-generated)
    bind = op.get_bind()
    insp = sa.inspect(bind)
    for fk in insp.get_foreign_keys("build"):
        cols = tuple(fk.get("constrained_columns") or ())
        if "firmware_min_id" in cols or "firmware_max_id" in cols:
            op.drop_constraint(fk["name"], "build", type_="foreignkey")

    # 6) Drop the new columns
    op.drop_column("build", "firmware_max_id")
    op.drop_column("build", "firmware_min_id")
