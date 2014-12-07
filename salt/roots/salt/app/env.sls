env-packages:
  pkg.installed:
    - pkgs:
      - git
      - python-virtualenv
      - python3-dev
      - libffi-dev

app-env:
  virtualenv.managed:
    - name: {{ pillar['env_path'] }}
    - python: /usr/bin/python3
    - cwd: {{ pillar['app_path'] }}
    - requirements: {{ pillar['app_path'] }}/requirements.txt
    - require:
      - pkg: env-packages
