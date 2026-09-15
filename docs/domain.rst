Domain Layer
============
.. module:: spkrepo.domain

Pure business logic with no Flask, database, filesystem, or network access.
Adapters (:doc:`utils`, :doc:`operations`, views, CLI) resolve
infrastructure state and delegate here; see each module for the single
owner of every rule.

Shared Kernel
-------------
Fundamental value objects shared by all bounded contexts: architecture
translation, firmware/version parsing, filenames, display-name mapping.

.. automodule:: spkrepo.domain.shared_kernel
    :members:
    :undoc-members:

SPK Parsing
-----------
Strict and lenient ``.spk`` INFO/conf parsing over bytes and dicts
(the tar adapter ``spkrepo.utils.SPK`` handles archive I/O).

.. automodule:: spkrepo.domain.spk
    :members:
    :undoc-members:

Version Consistency
-------------------
Version-level metadata extraction and cross-build consistency checks.

.. automodule:: spkrepo.domain.versions
    :members:
    :undoc-members:

Upload
------
Conflict detection, permission decisions, firmware-range validation.

.. automodule:: spkrepo.domain.upload
    :members:
    :undoc-members:

Catalog
-------
Device-catalog shaping: firmware compat, quick-install flags, entry
construction, DSM grouping.

.. automodule:: spkrepo.domain.catalog
    :members:
    :undoc-members:

Downloads
---------
CDN log filtering, parsing, classification, and aggregation.

.. automodule:: spkrepo.domain.downloads
    :members:
    :undoc-members:

Access
------
Client-IP resolution behind the proxy chain.

.. automodule:: spkrepo.domain.access
    :members:
    :undoc-members:

Storage Policy
--------------
Upload preconditions and CDN URL shaping.

.. automodule:: spkrepo.domain.storage_policy
    :members:
    :undoc-members:

Ports
-----
Outbound contracts (``StoragePort``, ``CdnPort``, ``CachePort``) that
adapters implement and the application layer depends on.

.. automodule:: spkrepo.domain.ports
    :members:
    :undoc-members:
