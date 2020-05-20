# -*- coding: utf-8 -*-
from flask_caching import Cache
from flask_debugtoolbar import DebugToolbarExtension
from flask_mail import Mail
from flask_migrate import Migrate
from flask_security import Security
from flask_sqlalchemy import SQLAlchemy

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
