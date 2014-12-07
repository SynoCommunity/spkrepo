include:
  - .env

app-packages:
  pkg.installed:
    - pkgs:
      - python3

{{ pillar['config_path'] }}:
  file:
    - managed
    - source: salt://app/spkrepo.cfg.tmpl
    - makedirs: True
    - template: jinja

app-upgrade-database:
  cmd.run:
    - name: {{ pillar['env_path'] }}/bin/python manage.py db upgrade
    - cwd: {{ pillar['app_path'] }}
    - env:
      - SPKREPO_CONFIG: {{ pillar['config_path'] }}
    - require:
      - file: {{ pillar['config_path'] }}
      - virtualenv: app-env
