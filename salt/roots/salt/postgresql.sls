include:
  - app
  - app.env

postgresql:
  pkg:
    - installed
  service:
    - running
    - enable: True
    - require:
      - pkg: postgresql

postgresql-server-dev-9.3:
  pkg.installed

postgres-user:
  postgres_user.present:
    - name: {{ pillar['database']['user'] }}
    - password: '{{ pillar['database']['password'] }}'
    - require:
      - pkg: postgresql
    - require_in:
      - cmd: app-upgrade-database

postgres-database:
  postgres_database.present:
    - name: {{ pillar['database']['name'] }}
    - owner: {{ pillar['database']['user'] }}
    - require:
      - postgres_user: postgres-user
    - require_in:
      - cmd: app-upgrade-database

psycopg2:
  pip.installed:
    - bin_env: {{ pillar['env_path'] }}/bin/pip
    - require:
      - pkg: postgresql-server-dev-9.3
      - virtualenv: app-env
    - require_in:
      - cmd: app-upgrade-database
