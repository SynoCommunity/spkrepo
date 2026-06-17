# -*- coding: utf-8 -*-
import logging
import sys

import jinja2
from flask import Flask, request
from flask_admin import Admin

from . import config as default_config
from .cli import spkrepo as spkrepo_cli
from .ext import babel, cache, celery, db, debug_toolbar, mail, migrate, security
from .filters import register_filters
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
    TaskStatusView,
    UserView,
    VersionView,
    api,
    frontend,
    nas,
)

CACHEABLE_ENDPOINTS = {
    "nas.catalog",
    "nas.data",
    "frontend.index",
    "frontend.packages",
    "frontend.package",
}


def create_app(config=None, register_blueprints=True, init_admin=True):
    """Create a Flask app."""
    app = Flask("spkrepo")

    # Logging setup
    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handler.setFormatter(formatter)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # Avoid duplicate handlers if reloaded
    if not root.handlers:
        root.addHandler(handler)
    logging.getLogger("werkzeug").setLevel(logging.WARNING)
    logging.getLogger("boto3").setLevel(logging.WARNING)
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Configuration
    app.config.from_object(default_config)
    app.config.from_envvar("SPKREPO_CONFIG", silent=True)
    if config is not None:
        app.config.from_object(config)

    # Enable or disable Flask's subdomain routing per config
    app.subdomain_matching = app.config.get("SUBDOMAIN_MATCHING", False)

    # Disable strict slashes
    app.url_map.strict_slashes = False

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
        admin.add_view(
            TaskStatusView(name="Task Status", endpoint="tasks", url="/admin/tasks/")
        )
        admin.init_app(app)

    # Commands
    app.cli.add_command(spkrepo_cli)

    # Core
    db.init_app(app)
    migrate.init_app(app, db, directory=app.config["MIGRATE_DIRECTORY"])

    # Auth
    security.init_app(app, user_datastore, register_form=SpkrepoRegisterForm)

    # Services
    mail.init_app(app)
    cache.init_app(app)
    babel.init_app(app)

    # Dev only
    if debug_toolbar is not None:
        debug_toolbar.init_app(app)

    # Jinja2 filters
    register_filters(app)

    # Celery
    celery.config_from_object(app.config.get("CELERY", {}))

    class FlaskTask(celery.Task):
        def __call__(self, *args, **kwargs):
            with app.app_context():
                return self.run(*args, **kwargs)

    celery.Task = FlaskTask
    app.extensions["celery"] = celery

    @app.after_request
    def set_cache_control(response):
        endpoint = request.endpoint or ""

        if (
            endpoint.startswith("security.")
            or request.path.startswith("/admin")
            or endpoint == "frontend.profile"
        ):
            response.headers["Cache-Control"] = "no-store, private"
        elif endpoint in CACHEABLE_ENDPOINTS:
            response.headers["Cache-Control"] = "public"
        return response

    return app
