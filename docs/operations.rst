Storage & Tasks
===============

Object Storage
--------------
The ``storage`` module manages SPK packages in S3-compatible object
storage. It handles uploading, downloading (rehoming),
and deleting package files, and is configured via the storage environment
variables described in :doc:`deployment`.

.. automodule:: spkrepo.storage
    :members:
    :undoc-members:

Background Tasks
----------------
Celery tasks are used for long-running operations triggered from the admin
interface. All tasks run on the ``ops`` queue and are tracked per-user via
Redis for 24 hours after completion. Task progress is visible on the
:ref:`Task Status <task-status>` page in the admin interface.

.. automodule:: spkrepo.views.tasks
    :members:
    :undoc-members:
