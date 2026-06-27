Utilities
=========
.. module:: spkrepo.utils

SPK
---
The :class:`SPK` class handles parsing and introspection of ``.spk`` package files.

.. autoclass:: SPK
    :members:
    :undoc-members:

Helpers
-------
These functions resolve reference data and apply SPK metadata to the database.

.. autofunction:: resolve_firmware
.. autofunction:: resolve_architectures
.. autofunction:: resolve_services
.. autofunction:: extract_version_metadata
.. autofunction:: apply_info_from_spk
.. autofunction:: apply_sidecar_to_db
.. autofunction:: populate_db
