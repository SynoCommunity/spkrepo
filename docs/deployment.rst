Deployment
==========

Architecture
------------
The production stack consists of:

- **PostgreSQL** — primary database
- **Redis** — Celery broker and Flask cache backend
- **Gunicorn** — WSGI server, reverse-proxied behind **nginx**
- **Celery worker** — processes background tasks on the ``ops`` queue
- **Celery beat** — scheduled task dispatcher
- **nginx** — reverse proxy and static file server
- **CDN** — edge caching for the NAS catalog endpoint
- **Object Storage** — S3-compatible storage (e.g. Fastly Object Storage) for SPK packages

Configuration
-------------
The ``SPKREPO_CONFIG`` environment variable points to a Python config file with production settings:

.. code-block:: console

    export SPKREPO_CONFIG=/etc/spkrepo/production.cfg

A minimal production config file looks like this:

.. code-block:: python

    SECRET_KEY = "replace-with-a-long-random-string"
    SQLALCHEMY_DATABASE_URI = "postgresql+psycopg2://spkrepo:password@db/spkrepo"
    CELERY_BROKER_URL = "redis://redis:6379/1"

    # S3-compatible object storage
    OBJECT_STORAGE_PACKAGES_ENDPOINT = "https://s3.example.com"
    OBJECT_STORAGE_PACKAGES_REGION = "us-east-1"
    OBJECT_STORAGE_PACKAGES_BUCKET = "spkrepo-packages"
    OBJECT_STORAGE_PACKAGES_ACCESS_KEY = "your-access-key"
    OBJECT_STORAGE_PACKAGES_SECRET_KEY = "your-secret-key"
    CDN_PURGE_TOKEN = "your-cdn-api-token"
    PACKAGES_CDN_HOST = "packages.example.com"

    # GPG signing
    GNUPG_PATH = "/path/to/gnupg-home"
    GNUPG_FINGERPRINT = "ABCDEF1234567890"
    GNUPG_TIMESTAMP_URL = "http://timestamp.synology.com/timestamp.php"

Gunicorn
--------
Run Gunicorn with enough workers to handle concurrent NAS catalog requests:

.. code-block:: console

    gunicorn "spkrepo:create_app()" \
        --workers 4 \
        --bind 0.0.0.0:8000 \
        --access-logfile - \
        --error-logfile -

nginx
-----
A minimal nginx reverse proxy configuration:

.. code-block:: nginx

    server {
        listen 80;
        server_name packages.example.com;

        client_max_body_size 200M;  # allow large SPK uploads

        location / {
            proxy_pass http://127.0.0.1:8000;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }
    }

Celery workers
--------------
Start the worker and beat scheduler:

.. code-block:: console

    # Worker (processes background tasks)
    uv run celery -A celery_app:celery_app worker -Q ops --loglevel=info

    # Beat (dispatches scheduled tasks)
    uv run celery -A celery_app:celery_app beat --loglevel=info

Database migrations
-------------------
Always run migrations before starting the application after an upgrade:

.. code-block:: console

    uv run flask db upgrade

See :doc:`migrations` for full migration reference.
