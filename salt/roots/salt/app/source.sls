include:
  - .env
  - uwsgi

{{ pillar['app_path'] }}:
  file.recurse:
    - source: salt://app/spkrepo
    - exclude_pat: E@\.py[oc]
    - exclude_pat: E@\.git/
    - require_in:
      - virtualenv: app-env

extend:
  uwsgi:
    service:
    - watch:
      - file: {{ pillar['app_path'] }}
