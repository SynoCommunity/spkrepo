Architecture
============

spkrepo follows a hexagonal (ports-and-adapters) layout. Dependencies point
inwards: transports depend on the application layer, which depends on the
domain, and the domain depends on nothing.

.. code-block:: text

    transports      views/ (Flask), cli.py (click), celery tasks
                    |
    application     orchestration use-cases (plan + execute)
                    |
    domain          pure business logic + port contracts
                    ^
                    | implemented by
    adapters        DB / filesystem / S3 / tar / GPG / HTTP I/O

Layers
------

**Domain** (``spkrepo.domain``)
    Pure functions and value objects: no Flask, database, filesystem, or
    network imports. This is where the business rules live (SPK parsing,
    firmware/version handling, conflict detection, catalog shaping, download
    aggregation). Importable without an application context — see
    :doc:`domain`.

**Application** (``spkrepo.application``)
    Use-case orchestration over the domain and the port contracts, still free
    of infrastructure imports. See :doc:`application`.

**Adapters** (``spkrepo.adapters``)
    All I/O: SPK tar handling, repository lookups, ORM writers, and seed data.
    Implements the ports declared in ``spkrepo.domain.ports``. See
    :doc:`utils`.

**Transports**
    Flask blueprints and Celery tasks in :doc:`operations` (``views/``,
    ``cli.py``). They resolve infrastructure state, call the application
    layer, and map results to HTTP flashes/status codes.

Where things live
-----------------

+---------------------------+----------------------------------------------+
| Concern                   | Module                                       |
+===========================+==============================================+
| SPK parse / INFO rules    | ``domain.spk``                               |
+---------------------------+----------------------------------------------+
| Version consistency       | ``domain.versions``                          |
+---------------------------+----------------------------------------------+
| Upload conflicts / authz  | ``domain.upload``                            |
+---------------------------+----------------------------------------------+
| NAS catalog shaping       | ``domain.catalog``                           |
+---------------------------+----------------------------------------------+
| CDN log aggregation       | ``domain.downloads``                         |
+---------------------------+----------------------------------------------+
| Client IP / storage rules | ``domain.access``, ``domain.storage_policy`` |
+---------------------------+----------------------------------------------+
| Activation decision       | ``application.activation``                   |
+---------------------------+----------------------------------------------+
| Tar I/O                   | ``adapters.spk_io``                          |
+---------------------------+----------------------------------------------+
| DB writers / lookups      | ``adapters.persistence``, ``repositories``   |
+---------------------------+----------------------------------------------+
| HTTP endpoints            | :doc:`api` (``views/api``, ``views/nas``)    |
+---------------------------+----------------------------------------------+
| Admin UI / actions        | :doc:`admin` (``views/admin``)               |
+---------------------------+----------------------------------------------+
| Background tasks          | :doc:`operations` (``views/tasks``)          |
+---------------------------+----------------------------------------------+

Testing
-------
Tests mirror the layering: ``test_domain`` / ``test_application`` are pure
units (no app, DB, or I/O), the remaining suites are integration tests of
one cross-boundary invariant each, and ``test_e2e`` covers two happy-path
workflows end to end.
