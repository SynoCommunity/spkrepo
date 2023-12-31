# spkrepo
Synology Package Repository

![Build](https://img.shields.io/github/actions/workflow/status/SynoCommunity/spkrepo/build.yml?branch=main&style=for-the-badge)
[![Discord](https://img.shields.io/discord/732558169863225384?color=7289DA&label=Discord&logo=Discord&logoColor=white&style=for-the-badge)](https://discord.gg/nnN9fgE7EF)


## Development
### Requirements
1. Install docker and docker-compose
2. Install python and poetry
3. Optionally install direnv and a working poetry layout as described [here](https://github.com/direnv/direnv/issues/592#issuecomment-856227234) in your `~/.config/direnv/direnvrc`

### Installation
1. Run postgres, e.g. using docker with `docker compose up db`
2. Install dependencies with `poetry install`
3. Run the next commands in the virtual environment `poetry shell`
4. Create the tables with `flask db upgrade`
5. Populate the database with some fake packages with `flask spkrepo populate_db`
6. Add a user with `flask spkrepo create_user -u admin -e admin@synocommunity.com -p adminadmin`
7. Grant the created user with Administrator permissions `flask roles add admin@synocommunity.com admin`
8. Grant the created user with Package Administrator permissions `flask roles add admin@synocommunity.com package_admin`
9. Grant the created user with Developer permissions `flask roles add admin@synocommunity.com developer`

To clean data created by fake packages, run `flask spkrepo depopulate_db`

### Run
1. Start postgres with `docker compose up db`
2. Start the development server with `flask run`
3. Website is available at http://localhost:5000
4. Admin interface is available at http://localhost:5000/admin
5. NAS interface is available at http://localhost:5000/nas
6. API is available at http://localhost:5000/api
7. Run the test suite with `pytest -v`

## Docker Compose Run
- If you also want to run the app in docker you can with `docker compose up app`
- You can run both postgres and the app with `docker compose up`


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
CACHE_TYPE= "SimpleCache"
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

## Add migration

```
cd migrations/
alembic revision -m "update build path length"
```
