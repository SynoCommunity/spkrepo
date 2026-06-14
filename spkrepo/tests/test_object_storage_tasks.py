# -*- coding: utf-8 -*-
import io
import os
from unittest.mock import patch

from flask import current_app

from spkrepo.ext import db
from spkrepo.models import Build
from spkrepo.tests.common import BaseTestCase, BuildFactory
from spkrepo.views.tasks import rehome_from_storage, upload_to_storage


class UploadToStorageTestCase(BaseTestCase):
    """Tests for upload_to_storage Celery task."""

    def test_success_sets_storage_remote(self):
        build = BuildFactory(signed=True, active=True)
        db.session.commit()
        with patch("spkrepo.views.tasks.storage.upload", return_value=True):
            result = upload_to_storage(build.id, str(build))
        self.assertEqual(result["status"], "ok")
        db.session.expire_all()
        self.assertEqual(db.session.get(Build, build.id).storage, "remote")

    def test_upload_failure_keeps_storage_local(self):
        build = BuildFactory(signed=True, active=True)
        db.session.commit()
        with patch("spkrepo.views.tasks.storage.upload", return_value=False):
            result = upload_to_storage(build.id, str(build))
        self.assertEqual(result["status"], "error")
        db.session.expire_all()
        self.assertEqual(db.session.get(Build, build.id).storage, "local")

    def test_skipped_when_not_signed(self):
        build = BuildFactory(signed=False)
        db.session.commit()
        result = upload_to_storage(build.id, str(build))
        self.assertEqual(result["status"], "error")
        self.assertIn("not signed", result["error"])

    def test_skipped_when_sidecar_exists(self):
        build = BuildFactory(signed=True, storage="remote")
        db.session.commit()
        sidecar = os.path.join(current_app.config["DATA_PATH"], build.path + ".json")
        with io.open(sidecar, "w") as f:
            f.write("{}")
        result = upload_to_storage(build.id, str(build))
        self.assertEqual(result["status"], "skipped")
        os.remove(sidecar)

    def test_stale_sidecar_is_cleaned(self):
        """Sidecar with storage=local should be removed and upload reprocessed."""
        build = BuildFactory(signed=True)
        db.session.commit()
        sidecar = os.path.join(current_app.config["DATA_PATH"], build.path + ".json")
        with io.open(sidecar, "w") as f:
            f.write("{}")
        result = upload_to_storage(build.id, str(build))
        self.assertNotEqual(result["status"], "skipped")
        self.assertFalse(os.path.exists(sidecar))

    def test_skipped_when_build_not_found(self):
        result = upload_to_storage(999999, "nonexistent")
        self.assertEqual(result["status"], "skipped")


class RehomeFromStorageTestCase(BaseTestCase):
    """Tests for rehome_from_storage Celery task."""

    def test_success_sets_storage_local(self):
        build = BuildFactory(storage="remote")
        db.session.commit()
        with patch("spkrepo.views.tasks.storage.download", return_value=True):
            result = rehome_from_storage(build.id, str(build))
        self.assertEqual(result["status"], "ok")
        db.session.expire_all()
        self.assertEqual(db.session.get(Build, build.id).storage, "local")

    def test_download_failure_keeps_storage_remote(self):
        build = BuildFactory(storage="remote")
        db.session.commit()
        with patch("spkrepo.views.tasks.storage.download", return_value=False):
            result = rehome_from_storage(build.id, str(build))
        self.assertEqual(result["status"], "error")
        db.session.expire_all()
        self.assertEqual(db.session.get(Build, build.id).storage, "remote")

    def test_skipped_when_build_not_found(self):
        result = rehome_from_storage(999999, "nonexistent")
        self.assertEqual(result["status"], "skipped")
