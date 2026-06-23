API Examples
============

All examples use ``http`` from the `HTTPie <https://httpie.io/>`_ package.

Authentication
--------------
Include your API key as the username in HTTP Basic Auth (no password):

.. code-block:: console

    http http://localhost:5000/api/packages --auth YOUR_API_KEY:

Upload a package
----------------
.. code-block:: console

    http --auth YOUR_API_KEY: POST http://localhost:5000/api/packages @package.spk

The API accepts an SPK file, parses its metadata, creates or updates the
package/version/build records, signs the SPK (if GNUPG_PATH is configured),
and stores the file. Pre-signed packages are rejected.

NAS catalog
-----------
The catalog endpoint returns available packages for a given architecture
and firmware version. Parameters are sent as POST form data:

.. code-block:: console

    http POST http://packages.synocommunity.com/ \\
        arch=apollolake \\
        build=25556 \\
        major=7 \\
        minor=2 \\
        micro=2 \\
        language=enu \\
        package_update_channel=stable

The response is a JSON array of package entries with download URLs,
descriptions, screenshots, and download counts.

List architectures
------------------
.. code-block:: console

    http http://localhost:5000/api/architectures

List firmware
-------------
.. code-block:: console

    http http://localhost:5000/api/firmware
