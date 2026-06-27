Models
======
.. module:: spkrepo.models

Referential
-----------
These models represent the fixed reference data that packages are built against.

.. autoclass:: Architecture
    :members:
    :undoc-members:

.. autoclass:: Firmware
    :members:
    :undoc-members:

.. autoclass:: Language
    :members:
    :undoc-members:

.. autoclass:: Service
    :members:
    :undoc-members:

Users
-----
.. autoclass:: User
    :members:
    :undoc-members:

.. autoclass:: Role
    :members:
    :undoc-members:

Core
----
The three-level hierarchy that represents a package in the repository:
a :class:`Package` has one or more :class:`Version` records, each of which
has one or more :class:`Build` records per architecture/firmware combination.

.. autoclass:: Package
    :members:
    :undoc-members:

.. autoclass:: Version
    :members:
    :undoc-members:

.. autoclass:: Build
    :members:
    :undoc-members:

Data
----
Supporting data attached to packages and builds.

.. autoclass:: Screenshot
    :members:
    :undoc-members:

.. autoclass:: DisplayName
    :members:
    :undoc-members:

.. autoclass:: BuildDescription
    :members:
    :undoc-members:

.. autoclass:: BuildManifest
    :members:
    :undoc-members:

.. autoclass:: Icon
    :members:
    :undoc-members:

Statistics
----------
.. autoclass:: DownloadStat
    :members:
    :undoc-members:

.. autoclass:: PackageDownloadCounts
    :members:
    :undoc-members:

Exceptions
----------
Exceptions raised by the spkrepo application layer.

.. module:: spkrepo.exceptions

.. autoclass:: SpkrepoError

.. autoclass:: SPKParseError

.. autoclass:: SPKSignError
