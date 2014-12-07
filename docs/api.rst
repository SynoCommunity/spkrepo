API
===
spkrepo exposes a `RESTful <http://en.wikipedia.org/wiki/Representational_state_transfer>`_ API and returns standard
HTTP Status Codes in all responses. Data is returned as JSON.

Authentication
--------------
To access the API, user must be registered, have the ``developer`` role and generated an API key from the profile
page. The :http:header:`Authorization` header is mandatory and must contain the API key as user with no password.
If the authentication fails, a :http:statuscode:`401` is returned.

.. warning::

   For security reasons, only **one** API key can be valid at a time. Should the API key be compromised,
   a new one can be generated from the profile page.


Errors
------
In case of ambiguous error, a detailed explaination is returned in JSON as ``message``

.. sourcecode:: http

   HTTP/1.1 422 UNPROCESSABLE ENTITY
   Content-Length: 43
   Content-Type: application/json

   {
       "message": "Unknown architecture: myarch"
   }


Endpoints
---------
.. autoflask:: spkrepo:create_app()
   :blueprints: api
