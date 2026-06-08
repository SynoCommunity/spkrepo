# -*- coding: utf-8 -*-
from celery import Celery
from flask_babel import Babel
from flask_caching import Cache
from flask_mail import Mail
from flask_migrate import Migrate
from flask_security import Security
from flask_sqlalchemy import SQLAlchemy

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
# Security
security = Security()
# SQLAlchemy
db = SQLAlchemy()

# Debug Toolbar — dev dependency, may not be installed in production
try:
    from flask_debugtoolbar import DebugToolbarExtension

    debug_toolbar = DebugToolbarExtension()
except ImportError:
    debug_toolbar = None
