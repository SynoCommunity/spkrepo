Persistence Adapters
====================
.. module:: spkrepo.adapters

Tar I/O, repository lookups, writers, and seed data, split out of the
former ``spkrepo.utils`` grab-bag during the hexagonal refactor.

SPK Archives
------------
Tar I/O for ``.spk`` files (parsing delegates to :doc:`domain`).

.. automodule:: spkrepo.adapters.spk_io
    :members:
    :undoc-members:

Repositories
------------
Resolve SPK INFO strings to database rows.

.. automodule:: spkrepo.adapters.repositories
    :members:
    :undoc-members:

Writers
-------
Apply SPK/sidecar metadata to ORM rows and files (upload/resync paths).

.. automodule:: spkrepo.adapters.persistence
    :members:
    :undoc-members:

Seed
----
Reference-data seed (architectures, firmware, languages, roles, services).

.. automodule:: spkrepo.adapters.seed
    :members:
    :undoc-members:
