Admin Interface
===============

Access at ``/admin/`` after logging in.

Dashboard
---------
The landing page shows repository totals (packages, builds, inactive
builds), the five most recent versions, and download charts broken down by
firmware, architecture, and package over the last 7, 30, and 90 days. Users
without the ``package_admin`` or ``admin`` role see figures scoped to the
packages they maintain.

Views
-----
.. list-table::
   :header-rows: 1
   :widths: 18 57 25

   * - View
     - Description
     - Required role
   * - Dashboard
     - Repository totals, recent versions, and download charts
     - ``developer``, ``package_admin``, ``admin``
   * - Task Status
     - Background task queue monitor
     - ``developer``, ``package_admin``, ``admin``
   * - Packages
     - Package metadata and maintainers
     - ``package_admin``
   * - Screenshots
     - Package screenshot images
     - ``package_admin``
   * - Architectures
     - Reference list of supported CPU architectures
     - ``package_admin``
   * - Firmware
     - Reference list of DSM / SRM firmware builds
     - ``package_admin``
   * - Services
     - Reference list of package service dependencies
     - ``package_admin``
   * - Versions
     - Package versions — activate/deactivate builds
     - ``developer`` or ``package_admin``
   * - Builds
     - Individual builds per architecture/firmware
     - ``developer`` or ``package_admin``
   * - Users
     - Manage user accounts and roles
     - ``admin``

A ``developer`` sees only the Versions and Builds of packages they maintain.
The Packages list has an ``Archived`` filter (all / active only / archived
only), and package, version, and build detail pages include previous/next
navigation that follows the originating list's sort and filters.

Actions
-------
Available actions appear in the dropdown after selecting items in a list view.
Sign and unsign require the ``admin`` role; upload, rehome, and resync
require ``admin`` or ``package_admin``. Deleting packages, versions, or
builds requires ``admin``.

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
