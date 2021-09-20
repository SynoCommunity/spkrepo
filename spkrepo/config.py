# -*- coding: utf-8 -*-
import os

DEBUG = True
TESTING = False
SECRET_KEY = "secret-key"
MAX_CONTENT_LENGTH = 170 * 1024 * 1024

# Application
DATA_PATH = os.path.realpath("data")
TEMPLATE_PATH = None
GNUPG_TIMESTAMP_URL = "http://timestamp.synology.com/timestamp.php"
GNUPG_PATH = None
GNUPG_FINGERPRINT = "gnupg-fingerprint"

# Security
SECURITY_CONFIRMABLE = True
SECURITY_REGISTERABLE = True
SECURITY_RECOVERABLE = True
SECURITY_CHANGEABLE = True
SECURITY_PASSWORD_HASH = "sha512_crypt"
SECURITY_PASSWORD_SALT = "password-salt"

# SQLAlchemy
SQLALCHEMY_ECHO = True
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SPKREPO_SQLALCHEMY_DATABASE_URI", "sqlite:///%s/spkrepo.db" % DATA_PATH
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Restful
HTTP_BASIC_AUTH_REALM = "spkrepo"

# Migrate
MIGRATE_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "migrations")
)

# Cache
CACHE_TYPE = "null"

# Debug Toolbar
DEBUG_TB_INTERCEPT_REDIRECTS = False
