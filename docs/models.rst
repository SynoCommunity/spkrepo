Models
======
.. module:: spkrepo.models

Referential
-----------
These models represent the fixed reference data that packages are built against.

.. autoclass:: Architecture
    :members:

.. autoclass:: Firmware
    :members:

.. autoclass:: Language
    :members:

.. autoclass:: Service
    :members:

Users
-----
.. autoclass:: User
    :members:

.. autoclass:: Role
    :members:

Core
----
The three-level hierarchy that represents a package in the repository:
a :class:`Package` has one or more :class:`Version` records, each of which
has one or more :class:`Build` records per architecture/firmware combination.

.. autoclass:: Package
    :members:

.. autoclass:: Version
    :members:

.. autoclass:: Build
    :members:

Data
----
Supporting data attached to packages and builds.

.. autoclass:: Screenshot
    :members:

.. autoclass:: DisplayName
    :members:

.. autoclass:: BuildDescription
    :members:

.. autoclass:: BuildManifest
    :members:

.. autoclass:: Icon
    :members:

Statistics
----------
.. autoclass:: DownloadStat
    :members:

.. autoclass:: PackageDownloadCounts
    :members:

Exceptions
----------
Exceptions raised by the spkrepo application layer.

.. module:: spkrepo.exceptions

.. autoclass:: SpkrepoError

.. autoclass:: SPKParseError

.. autoclass:: SPKSignError
