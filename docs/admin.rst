Admin Interface
===============

Access at ``/admin/`` after logging in. Views are role-scoped: the
reference lists (Architectures, Firmware, Services) need the
``package_admin`` role; Users needs ``admin``; Packages/Versions/Builds are
available to ``developer`` and ``package_admin`` (a ``developer`` only sees
packages they maintain).

Views
-----
+-----------------+----------------------------------------------------+
| View            | Description                                        |
+=================+====================================================+
| Users           | Manage user accounts and roles                     |
+-----------------+----------------------------------------------------+
| Architectures   | Reference list of supported CPU architectures      |
+-----------------+----------------------------------------------------+
| Firmware        | Reference list of DSM / SRM firmware builds        |
+-----------------+----------------------------------------------------+
| Services        | Reference list of package service dependencies     |
+-----------------+----------------------------------------------------+
| Screenshots     | Package screenshot images                          |
+-----------------+----------------------------------------------------+
| Packages        | Package metadata and maintainers                   |
+-----------------+----------------------------------------------------+
| Versions        | Package versions — activate/deactivate builds      |
+-----------------+----------------------------------------------------+
| Builds          | Individual builds per architecture/firmware        |
+-----------------+----------------------------------------------------+
| Task Status     | Background task queue monitor                      |
+-----------------+----------------------------------------------------+

Actions
-------
Available actions appear in the dropdown after selecting items in a list view.

**01 Activate (Users / Versions / Builds)**
    For Versions/Builds: marks the selected builds as active so they appear
    in the NAS catalog, and queues an upload when Object Storage is
    configured. If the SPK file has no GPG signature, the build is skipped
    with a warning. For Users: activates the account.

**02 Deactivate (Users / Versions / Builds)**
    For Versions/Builds: removes builds from the NAS catalog without deleting
    them. For Users: deactivates the account.

**03 Upload (Versions / Builds)**
    Uploads local SPK files to object storage (S3-compatible).
    Build must be local and signed. Inactive builds may be uploaded to
    free local disk space without appearing in the catalog.

**04 Rehome (Versions / Builds)**
    Downloads a build from object storage back to local disk for editing.
    Build must be inactive and in Object Storage.

**05 Resync Info (Versions / Builds)**
    Re-reads metadata (changelog, description, icons) from the local SPK file.

**06 Resync File (Versions / Builds)**
    Recalculates MD5 and file size from the local SPK.

**07 Sign (Versions / Builds)**
    Signs the SPK file with the configured GPG key.
    Requires ``GNUPG_PATH`` to be configured.

**08 Unsign (Versions / Builds)**
    Removes the GPG signature from the SPK file.
    Build must be deactivated first.

.. _task-status:

Task Status
-----------
The Task Status page shows the progress of background operations (upload,
rehome, resync). Tasks are tracked per-user via Redis and are retained
for 24 hours after completion. See :doc:`operations` for the underlying
task implementation.
