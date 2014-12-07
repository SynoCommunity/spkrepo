include:
  - app

{{ pillar['template_path'] }}:
  file.recurse:
    - source: salt://templates/templates
    - require_in:
      - cmd: app-upgrade-database
