include:
  - app

{{ pillar['gnupg_path'] }}:
  file.recurse:
    - source: salt://gnupg/home
    - require_in:
      - cmd: app-upgrade-database
