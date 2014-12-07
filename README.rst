spkrepo
=======
Synology Package Repository


.. image:: https://img.shields.io/travis/Diaoul/spkrepo.svg?style=flat
   :target: https://travis-ci.org/Diaoul/spkrepo
   :alt: Travis CI build status

.. image:: https://readthedocs.org/projects/spkrepo/badge/?version=latest&style=flat
   :target: http://spkrepo.readthedocs.org/en/latest
   :alt: Documentation Status

.. image:: https://img.shields.io/requires/github/Diaoul/spkrepo.svg?style=flat
   :target: https://requires.io/github/Diaoul/spkrepo/requirements/?branch=master
   :alt: Requirements Status

.. image:: https://img.shields.io/coveralls/Diaoul/spkrepo.svg?style=flat
   :target: https://coveralls.io/r/Diaoul/spkrepo?branch=master
   :alt: Code coverage


Development
-----------
Installation
~~~~~~~~~~~~
1. Create a virtualenv and install dev-requirements.txt. You may need to install development packages on your
   distribution.
2. Create the tables with ``python manage.py db create``
3. Populate the database with some fake packages with ``python manage.py db populate``
4. Add an user with ``python manage.py user create -u Admin -e admin@admin.adm -p adminadmin``
5. Grant the created user with admin permissions ``python manage.py user add_role -u admin@admin.adm -r admin``

To reset the environment, clean up with ``python manage.py clean``.

Run
~~~
1. Start the development server with ``python manage.py runserver``
2. Website is available at http://localhost:5000
3. Admin interface is available at http://localhost:5000/admin
4. NAS interface is available at http://localhost:5000/nas
5. API is available at http://localhost:5000/api
6. Run the test suite with ``python manage.py test``

Deployment
~~~~~~~~~~
As an example of deployment, spkrepo provides `SaltStack <http://www.saltstack.com/>`_ files in the ``salt`` directory.
You can test this with `Vagrant <https://www.vagrantup.com/>`_ by running ``vagrant up``. This makes easy to reproduce
production-like environments.

