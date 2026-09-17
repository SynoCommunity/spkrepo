Infrastructure
==============
Small adapter modules: request utilities, template helpers, mail, and the
CLI command group.

Networking
----------
Proxy-aware client-IP resolution (used for rate limiting).

.. automodule:: spkrepo.net
    :members:

Template Filters
----------------
Jinja2 helpers for the web frontend.

.. automodule:: spkrepo.filters
    :members:

Mail
----
Registration and notification mail with bot-template suppression.

.. automodule:: spkrepo.mail
    :members:

CLI
---
``flask spkrepo`` administrative commands (see :doc:`cli` for usage).

.. automodule:: spkrepo.cli
    :members:

Web Frontend
------------
HTML pages (not part of the device/API surface above): ``/`` landing,
``/packages`` with an architecture filter (persisted in a cookie),
``/package/<name>`` detail with version history, and ``/profile`` for
API-key management. Registration and login pages are provided by
Flask-Security with Turnstile bot protection.
