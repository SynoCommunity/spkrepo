# -*- coding: utf-8 -*-
from spkrepo import create_app

flask_app = create_app()
celery_app = flask_app.extensions["celery"]
