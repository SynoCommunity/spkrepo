nginx:
  pkg:
    - installed
  service:
    - running
    - enable: True
    - reload: True
    - watch:
      - file: /etc/nginx/sites-enabled/*
      - file: /etc/nginx/sites-available/*
    - require:
      - pkg: nginx

default-nginx:
  file.absent:
    - name: /etc/nginx/sites-enabled/default
    - require:
      - pkg: nginx

/etc/nginx/sites-available/{{ pillar['name'] }}.conf:
  file:
    - managed
    - source: salt://nginx/spkrepo.conf.tmpl
    - template: jinja
    - require:
      - pkg: nginx

/etc/nginx/sites-enabled/{{ pillar['name'] }}.conf:
  file:
    - symlink
    - target: /etc/nginx/sites-available/{{ pillar['name'] }}.conf
    - require:
      - file: /etc/nginx/sites-available/{{ pillar['name'] }}.conf
