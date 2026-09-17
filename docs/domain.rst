Domain Layer
============
.. module:: spkrepo.domain

Pure business logic with no Flask, database, filesystem, or network access.
Adapters (:doc:`utils`, :doc:`operations`, views, CLI) resolve
infrastructure state and delegate here; see each module for the single
owner of every rule.

Shared Kernel
-------------

.. automodule:: spkrepo.domain.shared_kernel
    :members:

SPK Parsing
-----------

.. automodule:: spkrepo.domain.spk
    :members:

Version Consistency
-------------------

.. automodule:: spkrepo.domain.versions
    :members:

Upload
------

.. automodule:: spkrepo.domain.upload
    :members:

Catalog
-------

.. automodule:: spkrepo.domain.catalog
    :members:

Downloads
---------

.. automodule:: spkrepo.domain.downloads
    :members:

Access
------

.. automodule:: spkrepo.domain.access
    :members:

Storage Policy
--------------

.. automodule:: spkrepo.domain.storage_policy
    :members:

Ports
-----

.. automodule:: spkrepo.domain.ports
    :members:
