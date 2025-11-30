# -*- coding: utf-8 -*-
import jinja2
from flask import Flask
from flask_admin import Admin
from wtforms import HiddenField

from . import config as default_config
from .cli import spkrepo as spkrepo_cli
from .ext import babel, cache, db, debug_toolbar, mail, migrate, security
from .models import user_datastore
from .views import (
    ArchitectureView,
    BuildView,
    FirmwareView,
    IndexView,
    PackageView,
    ScreenshotView,
    ServiceView,
    SpkrepoRegisterForm,
    UserView,
    VersionView,
    api,
    frontend,
    nas,
)


def create_app(config=None, register_blueprints=True, init_admin=True):
    """Create a Flask app"""
    app = Flask("spkrepo")

    # Configuration
    app.config.from_object(default_config)
    app.config.from_envvar("SPKREPO_CONFIG", silent=True)
    app.config.update(SECURITY_PASSWORD_CONFIRM_REQUIRED=False)

    # Enable or disable Flask’s subdomain routing per config
    app.subdomain_matching = app.config.get("SUBDOMAIN_MATCHING", False)

    # Disable strict slashes
    app.url_map.strict_slashes = False

    if config is not None:
        app.config.from_object(config)

    # Extra template path
    if app.config["TEMPLATE_PATH"] is not None:
        app.jinja_loader = jinja2.ChoiceLoader(
            [jinja2.FileSystemLoader(app.config["TEMPLATE_PATH"]), app.jinja_loader]
        )

    # Blueprints
    if register_blueprints:
        app.register_blueprint(frontend)
        app.register_blueprint(api, url_prefix="/api")
        app.register_blueprint(nas, url_prefix="/nas")

    # Admin
    if init_admin:
        admin = Admin(index_view=IndexView())
        admin.add_view(UserView())
        admin.add_view(ArchitectureView())
        admin.add_view(FirmwareView())
        admin.add_view(ServiceView())
        admin.add_view(ScreenshotView())
        admin.add_view(PackageView())
        admin.add_view(VersionView())
        admin.add_view(BuildView())
        admin.init_app(app)

    # Commands
    app.cli.add_command(spkrepo_cli)

    # Flask-Babel
    babel.init_app(app)

    # SQLAlchemy
    db.init_app(app)

    # Security
    security.init_app(app, user_datastore, register_form=SpkrepoRegisterForm)

    # Migrate
    migrate.init_app(app, db, directory=app.config["MIGRATE_DIRECTORY"])

    # Mail
    mail.init_app(app)

    # Cache
    cache.init_app(app)

    # Debug Toolbar
    debug_toolbar.init_app(app)

    # Jinja2 helpers
    @app.template_filter()
    def is_hidden_field(field):
        return isinstance(field, HiddenField)

    @app.template_filter()
    def sort_fields(form, field_names=None):
        fields = []
        for field in form:
            if field.name in field_names:
                fields.insert(field_names.index(field.name), field)
            else:
                fields.append(field)
        return fields

    return app
