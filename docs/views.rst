Views & Endpoints
=================

The transport layer. Endpoint documentation (HTTP request/response shapes)
lives in :doc:`api`; this page documents the module-level helpers.

Device Catalog
--------------

.. automodule:: spkrepo.views.nas
    :members:

Upload API
----------

.. automodule:: spkrepo.views.api
    :members:

Web Frontend
------------

.. automodule:: spkrepo.views.frontend
    :members:

Admin
-----
Flask-Admin copies its own members onto each view subclass, so autodoc would
list a large amount of framework API; the views are therefore summarised
here and described in :doc:`admin`. The reusable mixins and helpers are
documented in full.

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

.. automodule:: spkrepo.app
    :members:

Configuration
-------------

.. automodule:: spkrepo.config
    :members:

Extensions
----------
The module is documented without enumerating members: the extension
singletons are data, and ``SpkrepoTask`` inherits Celery's ``Task`` whose
own docstrings use roles this project does not register.

.. automodule:: spkrepo.ext
    :no-members:

.. autoclass:: spkrepo.ext.SpkrepoTask
    :no-members:
