# -*- coding: utf-8 -*-
from flask.ext.cache import Cache
from flask.ext.debugtoolbar import DebugToolbarExtension
from flask.ext.mail import Mail
from flask.ext.migrate import Migrate
from flask.ext.security import Security
from flask.ext.sqlalchemy import SQLAlchemy

# Cache
cache = Cache()

# Debug Toolbar
debug_toolbar = DebugToolbarExtension()

# Mail
mail = Mail()

# Migrate
migrate = Migrate()

# Security
security = Security()

# SQLAlchemy
db = SQLAlchemy()
