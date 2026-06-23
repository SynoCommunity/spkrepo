Admin Interface
===============

Access at ``/admin/`` after logging in with an admin account.

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

**01 Activate (Versions / Builds)**
    Marks the selected builds as active so they appear in the NAS catalog.
    If the SPK file has no GPG signature, the build is skipped with a warning.

**02 Deactivate (Versions / Builds)**
    Removes builds from the NAS catalog without deleting them.

**03 Upload (Versions / Builds)**
    Uploads local SPK files to object storage (S3-compatible).
    Build must be local, active, and signed.

**04 Rehome (Versions / Builds)**
    Downloads a build from object storage back to local disk for editing.

**05 Resync Info (Versions / Builds)**
    Re-reads metadata (changelog, description, icons) from the local SPK file.

**06 Resync File (Versions / Builds)**
    Recalculates MD5 and file size from the local SPK.

**07 Sign (Builds)**
    Signs the SPK file with the configured GPG key.
    Requires ``GNUPG_PATH`` to be configured.

**08 Unsign (Builds)**
    Removes the GPG signature from the SPK file.
    Build must be deactivated first.

Task Status
-----------
The Task Status page shows the progress of background operations (upload,
rehome, resync). Tasks are tracked per-user via Redis and are retained
for 24 hours after completion.
