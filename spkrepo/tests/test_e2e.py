# -*- coding: utf-8 -*-
"""E2E happy paths: component wiring only, no edge cases.

Each test exercises a full workflow across boundaries (API -> admin ->
catalog/download, storage round-trip). Branch logic is covered in
test_domain.py + integration suites; these assert the pieces connect.
"""

import json
import os
from unittest.mock import patch

from flask import current_app, url_for

from spkrepo.ext import db
from spkrepo.models import Architecture, Build, Firmware, Role
from spkrepo.tests.common import (
    BaseTestCase,
    BuildFactory,
    UserFactory,
    create_spk,
    run_task_sync,
)
from spkrepo.tests.test_api import authorization_header, get_only_build
from spkrepo.views.tasks import rehome_from_storage, upload_to_storage


def _upload_template(client, user, template):
    """POST a build template's SPK, return the response."""
    with create_spk(template) as spk:
        return client.post(
            url_for("api.packages"),
            headers=authorization_header(user),
            data=spk.read(),
        )


def _sign(build):
    """Simulate the GPG sign step (out of scope: needs timestamp server)."""
    build.signed = True
    db.session.commit()


def _activate_build(case, build):
    """Activate one build via the Flask-Admin build action."""
    with case.logged_user("package_admin"):
        response = case.client.post(
            url_for("build.action_view"),
            follow_redirects=True,
            data=dict(action="01_activate", rowid=[build.id]),
        )
    case.assert200(response)
    assert "activated" in response.data.decode()
    db.session.expire_all()
    assert db.session.get(Build, build.id).active is True


def _catalog_entry_for(case, arch, fw_build, package_name):
    response = case.client.post(
        url_for("nas.catalog"),
        data=dict(arch=arch, build=str(fw_build), language="enu"),
    )
    case.assert200(response)
    payload = json.loads(response.data.decode())
    packages = payload if isinstance(payload, list) else payload["packages"]
    return next(p for p in packages if p["package"] == package_name)


class UploadCatalogDownloadE2E(BaseTestCase):
    """POST /api/packages -> sign -> activate -> catalog -> download."""

    def test_upload_activate_catalog_download(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()
        template = BuildFactory.build(
            architectures=[Architecture.find("88f628x")],
            firmware_min=Firmware.find(1594),
            version__report_url=None,
        )
        response = _upload_template(self.client, user, template)
        self.assert201(response)

        build = get_only_build()
        self.assertFalse(build.active)
        _sign(build)
        _activate_build(self, build)

        entry = _catalog_entry_for(self, "88f6281", 1594, build.version.package.name)
        assert entry["version"] == build.version.version_string

        download = self.client.get(url_for("nas.data", path=build.path))
        self.assert200(download)
        assert len(download.data) > 0


class StorageRoundTripE2E(BaseTestCase):
    """Activate (queues upload) -> upload_to_storage -> rehome."""

    def test_activate_upload_rehome(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()
        template = BuildFactory.build(
            architectures=[Architecture.find("88f628x")],
            firmware_min=Firmware.find(1594),
            version__report_url=None,
        )
        self.assert201(_upload_template(self.client, user, template))
        build = get_only_build()
        _sign(build)

        # Activate with Object Storage enabled: the admin action must queue
        # upload_to_storage; .delay runs the task synchronously here, so the
        # whole action -> Celery -> S3 (mocked) seam is exercised.
        with (
            patch(
                "spkrepo.views.admin.storage_service.storage_configured",
                return_value=True,
            ),
            patch(
                "spkrepo.views.admin.upload_to_storage.delay",
                side_effect=run_task_sync(upload_to_storage.run),
            ),
            patch("spkrepo.views.tasks.storage.upload", return_value=True),
        ):
            with self.logged_user("package_admin"):
                response = self.client.post(
                    url_for("build.action_view"),
                    follow_redirects=True,
                    data=dict(action="01_activate", rowid=[build.id]),
                )
        self.assert200(response)
        db.session.expire_all()
        refreshed = db.session.get(Build, build.id)
        self.assertTrue(refreshed.active)
        self.assertEqual(refreshed.storage, "remote")

        local_path = os.path.join(current_app.config["DATA_PATH"], build.path)
        assert not os.path.exists(local_path)

        # Rehome needs a file to download into place; simulate S3 by
        # recreating the local artifact via the download mock's side effect.
        def _fake_download(_key, dest):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(b"spk-bytes")
            return True

        with (
            patch("spkrepo.views.tasks.storage.download", side_effect=_fake_download),
            patch("spkrepo.views.tasks.storage.delete", return_value=True),
            patch("spkrepo.views.tasks.storage.purge_cdn"),
        ):
            result = rehome_from_storage(build.id, str(build))
        assert result["status"] == "ok"
        db.session.expire_all()
        assert db.session.get(Build, build.id).storage == "local"
