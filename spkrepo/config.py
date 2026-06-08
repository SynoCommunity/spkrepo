# -*- coding: utf-8 -*-
import os

DEBUG = False
TESTING = False
SECRET_KEY = "secret-key"
MAX_CONTENT_LENGTH = 170 * 1024 * 1024

# Enable subdomain-based routing (False in local dev; True in prod)
SUBDOMAIN_MATCHING = False

# Application
DATA_PATH = os.path.realpath("data")
TEMPLATE_PATH = None
GNUPG_TIMESTAMP_URL = "http://timestamp.synology.com/timestamp.php"
GNUPG_PATH = None
GNUPG_FINGERPRINT = "gnupg-fingerprint"

# Object Storage (S3-compatible)
OBJECT_STORAGE_ENDPOINT = "https://us-east.object.fastlystorage.app"
OBJECT_STORAGE_REGION = "us-east"
OBJECT_STORAGE_BUCKET = "your-log-bucket"
OBJECT_STORAGE_PREFIX = "logs/"
OBJECT_STORAGE_ACCESS_KEY = "your-read-key"
OBJECT_STORAGE_SECRET_KEY = "your-read-secret"

# Security
SECURITY_CONFIRMABLE = True
SECURITY_REGISTERABLE = True
SECURITY_RECOVERABLE = True
SECURITY_CHANGEABLE = True
SECURITY_PASSWORD_HASH = "sha512_crypt"
SECURITY_PASSWORD_SALT = "password-salt"
SECURITY_PASSWORD_CONFIRM_REQUIRED = False

# SQLAlchemy
SQLALCHEMY_ECHO = False
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SPKREPO_SQLALCHEMY_DATABASE_URI",
    "postgresql+psycopg2://spkrepo:spkrepo@localhost/spkrepo",
)
SQLALCHEMY_TRACK_MODIFICATIONS = False

# Restful
HTTP_BASIC_AUTH_REALM = "spkrepo"

# Migrate
MIGRATE_DIRECTORY = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "migrations")
)

# Cache
CACHE_TYPE = "redis"
CACHE_REDIS_HOST = "localhost"

# Tasks
CELERY = {
    "broker_url": os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/1"),
    "result_backend": os.environ.get(
        "CELERY_RESULT_BACKEND", "redis://localhost:6379/1"
    ),
    "result_expires": 86400,  # clean up task results after 24 hours
    "task_queues": {
        "celery": {},  # default queue for anything else
        "resync": {},  # resync tasks — isolated so they can't starve other work
    },
    "task_default_queue": "celery",
}

# Debug Toolbar
DEBUG_TB_INTERCEPT_REDIRECTS = False
