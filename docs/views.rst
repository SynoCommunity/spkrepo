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

Admin
-----
``views/admin`` implements the Flask-Admin interface described in
:doc:`admin`. Flask-Admin copies its own members onto each view subclass, so
autodoc would list a large amount of framework API; the views are therefore
summarised here and described in the guide. The reusable mixins and helpers
are documented in full.

.. automodule:: spkrepo.views.admin
    :no-members:

.. autofunction:: spkrepo.views.admin.screenshot_namegen

.. autoclass:: spkrepo.views.admin.SignResyncMixin
    :members:

.. autoclass:: spkrepo.views.admin.MaintainerScopedMixin
    :members:

.. autoclass:: spkrepo.views.admin.DetailsNavigationMixin
    :members:

.. autoclass:: spkrepo.views.admin.IndexView
    :no-members:

.. autoclass:: spkrepo.views.admin.TaskStatusView
    :no-members:

.. autoclass:: spkrepo.views.admin.UserView
    :no-members:

.. autoclass:: spkrepo.views.admin.ArchitectureView
    :no-members:

.. autoclass:: spkrepo.views.admin.FirmwareView
    :no-members:

.. autoclass:: spkrepo.views.admin.ServiceView
    :no-members:

.. autoclass:: spkrepo.views.admin.ScreenshotView
    :no-members:

.. autoclass:: spkrepo.views.admin.PackageView
    :no-members:

.. autoclass:: spkrepo.views.admin.VersionView
    :no-members:

.. autoclass:: spkrepo.views.admin.BuildView
    :no-members:


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
