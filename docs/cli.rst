CLI Commands
============

Run via ``flask spkrepo <command>`` inside the app's environment.

Commands
--------

**create_user**
    Create a new user with an activated account.

    Options: ``-u/--username``, ``-e/--email``, ``-p/--password``
    (all prompted if omitted).

**create_admin**
    Create a new super admin user, assigning the ``admin``,
    ``package_admin``, and ``developer`` roles. Skips user creation if a
    user with the given email already exists.

    Options: ``-u/--username`` (default ``admin``), ``-e/--email``
    (default ``admin@synocommunity.com``), ``-p/--password`` (prompted).

**populate_db**
    Populate the database with sample packages, for local development.

**depopulate_db**
    Delete all packages from the database and file system. Refuses to
    run if any build has been uploaded to Object Storage.

**clean**
    Remove all package files under ``DATA_PATH`` without touching the
    database. Like ``depopulate_db``, refuses to run if any build has
    been uploaded to Object Storage.

**ingest_logs**
    Ingest download stats from Object Storage log files and refresh the
    download-count materialized view. Schedule hourly (e.g. a cron job
    or scheduler invoking ``flask spkrepo ingest_logs``) — see
    :doc:`operations`.
