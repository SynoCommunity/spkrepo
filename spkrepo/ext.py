# -*- coding: utf-8 -*-
"""Flask extension singletons, initialised in :func:`spkrepo.app.create_app`."""

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


class SpkrepoTask(celery.Task):
    """Celery task base that runs each task inside the current app context.

    The app is resolved at call time from ``celery.spkrepo_app`` (set by
    :func:`spkrepo.app.create_app`) rather than captured in a closure. This
    keeps it correct when create_app() runs more than once (tests) and when
    a task class is finalised before create_app() has run — both of which
    left the base as the plain ``Task`` with a closed-over/dead app before.
    """

    def __call__(self, *args, **kwargs):
        app = getattr(celery, "spkrepo_app", None)
        if app is None:
            return self.run(*args, **kwargs)
        with app.app_context():
            return self.run(*args, **kwargs)


# Set before any ``@celery.task`` is declared (ext is imported first) so task
# classes always inherit the app-context-running base.
celery.Task = SpkrepoTask
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
