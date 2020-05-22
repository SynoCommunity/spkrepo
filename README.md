spkrepo
=======
Synology Package Repository


![Build](https://github.com/SynoCommunity/spkrepo/workflows/Build/badge.svg)


## Development
### Installation

1. Install dependencies with `poetry install`
2. Create the tables with `python manage.py db create`
3. Populate the database with some fake packages with `python manage.py db populate`
4. Add an user with `python manage.py user create -u Admin -e admin@admin.adm -p adminadmin`
5. Grant the created user with admin permissions `python manage.py user add_role -u admin@admin.adm -r admin`

To reset the environment, clean up with `python manage.py clean`.

### Run
1. Start the development server with `python manage.py runserver`
2. Website is available at http://localhost:5000
3. Admin interface is available at http://localhost:5000/admin
4. NAS interface is available at http://localhost:5000/nas
5. API is available at http://localhost:5000/api
6. Run the test suite with `python manage.py test`

## Deployment
### Docker
Example usage:
```bash
docker run -it --rm --name spkrepo -v $(pwd)/data:/data -v $(pwd)/docker-config.py:/usr/src/app/spkrepo/config.py -p 8000:8000 synocommunity/spkrepo
```
