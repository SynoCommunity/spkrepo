include:
  - app

uwsgi:
  pkg.installed:
    - pkgs:
      - uwsgi
      - uwsgi-plugin-python3
  service:
    - running
    - enable: True
    - watch:
      - file: /etc/uwsgi/apps-available/*
      - file: /etc/uwsgi/apps-enabled/*
      - file: {{ pillar['config_path'] }}
    - require:
      - pkg: uwsgi

/etc/uwsgi/apps-available/{{ pillar['name'] }}.ini:
  file:
    - managed
    - source: salt://uwsgi/uwsgi.ini
    - template: jinja
    - require:
      - pkg: uwsgi

/etc/uwsgi/apps-enabled/{{ pillar['name'] }}.ini:
  file:
    - symlink
    - target: /etc/uwsgi/apps-available/{{ pillar['name'] }}.ini
    - require:
      - file: /etc/uwsgi/apps-available/{{ pillar['name'] }}.ini
      - cmd: app-upgrade-database
