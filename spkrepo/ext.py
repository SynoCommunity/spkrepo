# -*- coding: utf-8 -*-
from celery import Celery
from flask_babel import Babel
from flask_caching import Cache
from flask_limiter import Limiter
from flask_mail import Mail
from flask_migrate import Migrate
from flask_security import Security
from flask_sqlalchemy import SQLAlchemy

from .mail import SpkrepoMailUtil
from .net import get_client_ip

# Flask-Babel
babel = Babel()
# Cache
cache = Cache()
# Celery
celery = Celery()
# Mail
mail = Mail()
# Migrate
migrate = Migrate()
# Rate limiting (storage backend comes from RATELIMIT_STORAGE_URI app config;
# per-endpoint limits are applied to views in create_app)
limiter = Limiter(key_func=get_client_ip)
# Security (custom MailUtil suppresses bot-triggered registration emails)
security = Security(mail_util_cls=SpkrepoMailUtil)
# SQLAlchemy
db = SQLAlchemy()

# Debug Toolbar — dev dependency, may not be installed in production
try:
    from flask_debugtoolbar import DebugToolbarExtension

    debug_toolbar = DebugToolbarExtension()
except ImportError:
    debug_toolbar = None
