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

# Object Storage — Logs (S3-compatible)
OBJECT_STORAGE_LOGS_ENDPOINT = "https://us-east.object.fastlystorage.app"
OBJECT_STORAGE_LOGS_REGION = "us-east"
OBJECT_STORAGE_LOGS_BUCKET = "your-log-bucket"
OBJECT_STORAGE_LOGS_PREFIX = "logs/"
OBJECT_STORAGE_LOGS_ACCESS_KEY = "your-read-key"
OBJECT_STORAGE_LOGS_SECRET_KEY = "your-read-secret"

# Object Storage — Packages (S3-compatible, separate bucket)
OBJECT_STORAGE_PACKAGES_ENDPOINT = None
OBJECT_STORAGE_PACKAGES_REGION = None
OBJECT_STORAGE_PACKAGES_BUCKET = None
OBJECT_STORAGE_PACKAGES_ACCESS_KEY = None
OBJECT_STORAGE_PACKAGES_SECRET_KEY = None

# CDN
CDN_PURGE_TOKEN = None
PACKAGES_CDN_HOST = None

# Cloudflare Turnstile (bot protection on registration). Only the secret is
# sensitive — the site key and hostname are public. Set real values in the
# production config; when unset, registration fail-closes (see
# SpkrepoRegisterForm).
TURNSTILE_SITE_KEY = None
TURNSTILE_SECRET_KEY = os.environ.get("TURNSTILE_SECRET_KEY")
# Hostname the Turnstile widget is registered for (e.g. "example.com").
# When set, the siteverify response hostname must match; when unset the
# check is skipped (dev/test).
TURNSTILE_HOSTNAME = None

# Security
SECURITY_CACHE_CONTROL = {}
SECURITY_CONFIRMABLE = True
SECURITY_REGISTERABLE = True
SECURITY_RECOVERABLE = True
SECURITY_CHANGEABLE = True
SECURITY_PASSWORD_HASH = "sha512_crypt"
SECURITY_PASSWORD_SALT = "password-salt"
SECURITY_PASSWORD_CONFIRM_REQUIRED = False
# Return generic responses for auth endpoints so bots can't enumerate which
# emails/usernames are registered (and email owners when attempts occur).
SECURITY_RETURN_GENERIC_RESPONSES = True

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
CACHE_TYPE = "flask_caching.backends.RedisCache"
CACHE_REDIS_HOST = "localhost"

# Rate limiting (per-IP, proxy-aware via get_client_ip). Dedicated DB 2 keeps
# counters isolated from the cache (DB 0) and Celery (DB 1); shared across
# gunicorn workers, with memory fallback covering redis outages. Tests
# override the URI to memory:// (see tests/common.py).
RATELIMIT_STORAGE_URI = "redis://localhost:6379/2"
RATELIMIT_IN_MEMORY_FALLBACK_ENABLED = True

# Tasks
CELERY = {
    "broker_url": "redis://localhost:6379/1",
    "result_backend": "redis://localhost:6379/1",
    "result_expires": 86400,  # clean up task results after 24 hours
    "task_queues": {
        "celery": {},  # default queue for anything else
        "ops": {},  # admin-triggered background operations (upload, rehome, resync)
    },
    "task_default_queue": "celery",
}

# Debug Toolbar
DEBUG_TB_INTERCEPT_REDIRECTS = False
