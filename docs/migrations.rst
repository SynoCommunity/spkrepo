Database Migrations
===================

Migrations use `Alembic <https://alembic.sqlalchemy.org/>`_ via Flask-Migrate.

Creating a migration
--------------------
.. code-block:: console

    # Auto-generate from model changes
    uv run flask db migrate -m "description of changes"

    # Review the generated file in migrations/versions/

Running migrations
------------------
.. code-block:: console

    # Upgrade to the latest revision
    uv run flask db upgrade

    # Upgrade / downgrade one step
    uv run flask db upgrade +1
    uv run flask db downgrade -1

    # Downgrade to base (roll back all migrations)
    uv run flask db downgrade base

Portability notes
-----------------
Migrations must work on both **PostgreSQL** (production) and **SQLite** (tests).
When using PostgreSQL-specific features, guard them with a dialect check:

.. code-block:: python

    def upgrade() -> None:
        is_pg = op.get_bind().engine.dialect.name == "postgresql"
        if is_pg:
            op.execute("CREATE MATERIALIZED VIEW ...")

Batch mode (for column alterations) is enabled automatically on SQLite.
Explicit constraint names are required for batch mode to work.

Revision history
----------------
All migrations are in ``migrations/versions/``. Each file is prefixed with
its revision ID and a short description.
