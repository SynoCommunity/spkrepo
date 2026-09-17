Views & Endpoints
=================

The transport layer. Endpoint documentation (HTTP request/response shapes)
lives in :doc:`api`; this page documents the module-level helpers.

Device Catalog
--------------
``views/nas`` serves the catalog that DSM/SRM devices poll and the file
endpoint they download from.

.. automodule:: spkrepo.views.nas
    :members:

Upload API
----------
``views/api`` implements ``POST /api/packages``.

.. automodule:: spkrepo.views.api
    :members:

Web Frontend
------------
``views/frontend`` renders the HTML pages (landing, package list/detail,
profile) and the registration form.

.. automodule:: spkrepo.views.frontend
    :members:

Application Factory
-------------------
``app.create_app`` wires the extensions and blueprints.

.. automodule:: spkrepo.app
    :members:

Configuration
-------------
``config`` holds the default settings; production overrides are loaded from
the ``SPKREPO_CONFIG`` file (see :doc:`deployment`).

.. automodule:: spkrepo.config
    :members:

Extensions
----------
``ext`` holds the Flask extension singletons initialised by ``create_app``,
plus the Celery task base used by the background tasks.

The module is documented without enumerating members: the extension
singletons are data, and ``SpkrepoTask`` inherits Celery's ``Task`` whose own
docstrings use roles this project does not register.

.. automodule:: spkrepo.ext
    :no-members:

.. autoclass:: spkrepo.ext.SpkrepoTask
    :no-members:
