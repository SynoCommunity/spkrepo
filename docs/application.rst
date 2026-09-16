Application Layer
=================
.. module:: spkrepo.application

Use-case orchestration over the :doc:`domain` layer and ports. Transports
(views, tasks, CLI) resolve infrastructure state, then call these
planners — no Flask, database, or network access here.

Activation
----------
Decides which builds activate and queue for upload
(used by both admin activate actions).

.. automodule:: spkrepo.application.activation
    :members:
    :undoc-members:
