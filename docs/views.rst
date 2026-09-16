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
    :undoc-members:

Upload API
----------
``views/api`` implements ``POST /api/packages``.

.. automodule:: spkrepo.views.api
    :members:
    :undoc-members:

Web Frontend
------------
``views/frontend`` renders the HTML pages (landing, package list/detail,
profile) and the registration form.

.. automodule:: spkrepo.views.frontend
    :members:
    :undoc-members:

Application Factory
-------------------
``app.create_app`` wires the extensions and blueprints.

.. automodule:: spkrepo.app
    :members:
    :undoc-members:

Configuration
-------------
``config`` holds the default settings; production overrides are loaded from
the ``SPKREPO_CONFIG`` file (see :doc:`deployment`).

.. automodule:: spkrepo.config
    :members:
    :undoc-members:

Extensions
----------
``ext`` holds the Flask extension singletons initialised by ``create_app``.

.. automodule:: spkrepo.ext
    :members:
    :undoc-members:
