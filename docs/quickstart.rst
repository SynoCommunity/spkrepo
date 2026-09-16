Quickstart
==========

Prerequisites
-------------
- Docker and Docker Compose
- Python 3.14 or later
- `uv <https://docs.astral.sh/uv/>`_ (package manager)

Setup
-----
.. code-block:: console

    # Clone the repository
    git clone https://github.com/SynoCommunity/spkrepo
    cd spkrepo

    # Create virtual environment and install dependencies
    uv sync --locked --all-extras

    # Start PostgreSQL and Redis (Docker)
    docker compose up -d db redis

    # Run database migrations (also inserts reference data: architectures,
    # firmware, languages, roles, services)
    uv run flask db upgrade

    # Load sample packages for local development
    uv run flask spkrepo populate_db

    # Start the development server
    uv run flask run -h 0.0.0.0

The application will be available at http://localhost:5000.

Register an admin user
----------------------
.. code-block:: console

    uv run flask spkrepo create_admin

Environment Variables
---------------------
Most settings come from a config file pointed to by ``SPKREPO_CONFIG``
(see :doc:`deployment`); the handful read from the environment are:

.. code-block:: text

    SPKREPO_CONFIG                    None (uses built-in defaults)
    SPKREPO_SQLALCHEMY_DATABASE_URI   postgresql+psycopg2://spkrepo:spkrepo@localhost/spkrepo
    TURNSTILE_SECRET_KEY              None (registration fail-closes when unset)

Celery uses the ``CELERY`` config dict (``broker_url`` defaults to
``redis://localhost:6379/1`` — see :doc:`deployment`).
