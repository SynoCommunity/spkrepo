# spkrepo
Synology Package Repository

![Build](https://img.shields.io/github/workflow/status/SynoCommunity/spkrepo/Build?style=for-the-badge)
[![Discord](https://img.shields.io/discord/732558169863225384?color=7289DA&label=Discord&logo=Discord&logoColor=white&style=for-the-badge)](https://discord.gg/nnN9fgE7EF)


## Development
### Installation
1. Install dependencies with `poetry install`
2. Run the next commands in the virtual environment `poetry shell`
3. Create the tables with `python manage.py db create`
4. Populate the database with some fake packages with `python manage.py db populate`
5. Add an user with `python manage.py user create -u Admin -e admin@admin.adm -p adminadmin`
6. Grant the created user with Administrator permissions `python manage.py user add_role -u admin@admin.adm -r admin`
7. Grant the created user with Package Administrator permissions `python manage.py user add_role -u admin@admin.adm -r package_admin`
8. Grant the created user with Developer permissions `python manage.py user add_role -u admin@admin.adm -r developer`

To reset the environment, clean up with `python manage.py clean`.

### Run
1. Start the development server with `python manage.py runserver`
2. Website is available at http://localhost:5000
3. Admin interface is available at http://localhost:5000/admin
4. NAS interface is available at http://localhost:5000/nas
5. API is available at http://localhost:5000/api
6. Run the test suite with `poetry run pytest -v`

## Docker Compose Run
It is also possible to start a development environment with postgres database
using docker compose:
1. Build and run `docker-compose up --build`
2. On first run you can apply database migrations with `docker exec spkrepo_spkrepo_1 python manage.py db upgrade`.
   Also run any other command that you need (populate the databse, create user) as mentioned above but by prefixing
   with `docker exec {container_id} [...]`.
3. Browse to http://localhost:5000
4. To tear down the environment, run `docker-compose down --remove`

## Deployment

### Configuration
Create a config file `./config.py` to disable debug logs, connect to a database, set a secure key and optionally set a cache:

Use `LC_CTYPE=C tr -cd '[:print:]' < /dev/urandom | head -c 64` or `base64 < /dev/urandom | head -c 64` to get a random string

```python
DEBUG = False
TESTING = False
SECRET_KEY = "Please-change-me-to-some-random-string"
SQLALCHEMY_ECHO = False
SQLALCHEMY_DATABASE_URI = "postgresql://user:pass@localhost/dbname"
# https://pythonhosted.org/Flask-Caching/#configuring-flask-caching
CACHE_TYPE= "simple"
# For signing packages
GNUPG_PATH= "/usr/local/bin/gpg"
```


### Docker
Example usage:

```bash
docker run -it --rm --name spkrepo -v $(pwd)/data:/data -p 8000:8000 ghcr.io/synocommunity/spkrepo
```

Additional configuration can be mounted in the container and loaded by putting
the path into `SPKREPO_CONFIG` environment variable.

e.g.
```bash
docker run -it --rm --name spkrepo -v $(pwd)/data:/data -v $(pwd)/docker-config.py:/docker-config.py -e SPKREPO_CONFIG=/docker-config.py -p 8000:8000 ghcr.io/synocommunity/spkrepo
```


### Serve app via [a WSGI server](https://flask.palletsprojects.com/en/1.1.x/deploying/).
Example:

```bash
pip install gunicorn
SPKREPO_CONFIG="$PWD/config.py" gunicorn -w 4 'wsgi:app'
```
