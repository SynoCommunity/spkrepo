Quickstart
==========

Prerequisites
-------------
- Docker and Docker Compose
- Python 3.14
- `uv <https://docs.astral.sh/uv/>`_ (package manager)

Setup
-----
.. code-block:: console

    # Clone the repository
    git clone https://github.com/SynoCommunity/spkrepo
    cd spkrepo

    # Create virtual environment and install dependencies
    uv sync --locked --all-extras --dev

    # Start PostgreSQL and Redis (Docker)
    docker compose up -d db redis

    # Run database migrations
    uv run flask db upgrade

    # Seed the database with reference data
    uv run flask spkrepo populate_db

    # Start the development server
    uv run flask run -h 0.0.0.0

The application will be available at http://localhost:5000.

Register an admin user
----------------------
.. code-block:: console

    uv run flask spkrepo register_admin

Environment Variables
---------------------
.. code-block:: text

    SPKREPO_SQLALCHEMY_DATABASE_URI   postgresql+psycopg2://spkrepo:spkrepo@localhost/spkrepo
    SPKREPO_CONFIG                    None (uses built-in defaults)
    CELERY_BROKER_URL                 redis://localhost:6379/1
    SECRET_KEY                        None (required in production)
