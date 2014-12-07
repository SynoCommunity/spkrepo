# name
name: spkrepo

# paths
app_path: /var/www/spkrepo
env_path: /var/www/spkrepo/env
data_path: /var/www/spkrepo/data
config_path: /etc/spkrepo/spkrepo.cfg
template_path: /etc/spkrepo/templates
gnupg_path: None

# server name
server_name: localhost

# cache
cache:
  type: redis
  redis:
    db: 0

# database
database:
  type: postgresql
  name: spkrepo
  user: spkrepo
  password: spkrepo

# gnupg
gnupg_fingerprint: fingerprint

# application
debug: True
testing: False
secret_key: secret-key

# security
password_hash: plaintext
password_salt: password-salt
confirm_salt: confirm-salt
reset_salt: reset-salt
login_salt: login-salt
remember_salt: remember-salt
