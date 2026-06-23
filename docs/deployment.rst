Deployment
==========

Architecture
------------
The production stack consists of:

- **PostgreSQL** — primary database
- **Redis** — Celery broker and Flask cache backend
- **Gunicorn** — WSGI server, reverse-proxied behind **nginx**
- **Celery worker** — processes background tasks
- **Celery beat** — scheduled task dispatcher
- **nginx** — reverse proxy
- **CDN** — edge caching for the NAS catalog
- **Object Storage** — S3-compatible storage for SPK packages

Configuration
-------------
The ``SPKREPO_CONFIG`` environment variable points to a Python config file
with production settings. See the project wiki for reference configuration.
