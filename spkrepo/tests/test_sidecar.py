# -*- coding: utf-8 -*-
from spkrepo.ext import db
from spkrepo.models import Build
from spkrepo.tests.common import BaseTestCase, BuildFactory
from spkrepo.utils import apply_sidecar_to_db


class ApplySidecarToDBTestCase(BaseTestCase):
    def _make_sidecar(self, **overrides):
        sidecar = {
            "info": {
                "version": "1.2.3-4",
                "changelog": "Initial release",
                "checksum": "abc123",
            },
            "derived": {
                "install_wizard": True,
                "upgrade_wizard": False,
                "startable": True,
                "license": "MIT",
            },
            "calculated": {
                "md5": "d41d8cd98f00b204e9800998ecf8427e",
                "size": 1024,
            },
        }
        sidecar["info"].update(overrides.pop("info", {}))
        sidecar["derived"].update(overrides.pop("derived", {}))
        sidecar["calculated"].update(overrides.pop("calculated", {}))
        return sidecar

    def test_updates_version_metadata(self):
        build = BuildFactory()
        db.session.commit()
        apply_sidecar_to_db(db.session, build, self._make_sidecar())
        db.session.expire_all()
        refreshed = db.session.get(Build, build.id)
        assert refreshed.version.upstream_version == "1.2.3"
        assert refreshed.version.install_wizard is True
        assert refreshed.version.upgrade_wizard is False
        assert refreshed.version.startable is True
        assert refreshed.version.license == "MIT"

    def test_updates_build_metadata(self):
        build = BuildFactory()
        db.session.commit()
        apply_sidecar_to_db(db.session, build, self._make_sidecar())
        db.session.expire_all()
        refreshed = db.session.get(Build, build.id)
        assert refreshed.changelog == "Initial release"
        assert refreshed.checksum == "abc123"
        assert refreshed.md5 == "d41d8cd98f00b204e9800998ecf8427e"
        assert refreshed.size == 1024
        assert refreshed.signed is True
        assert refreshed.storage == "remote"

    def test_upstream_version_strips_build_number(self):
        build = BuildFactory()
        db.session.commit()
        sidecar = self._make_sidecar()
        sidecar["info"]["version"] = "5.6.7-89"
        apply_sidecar_to_db(db.session, build, sidecar)
        db.session.expire_all()
        refreshed = db.session.get(Build, build.id)
        assert refreshed.version.upstream_version == "5.6.7"

    def test_report_url_is_set(self):
        build = BuildFactory()
        db.session.commit()
        sidecar = self._make_sidecar()
        sidecar["info"]["report_url"] = "https://example.com/beta"
        apply_sidecar_to_db(db.session, build, sidecar)
        db.session.expire_all()
        refreshed = db.session.get(Build, build.id)
        assert refreshed.version.report_url == "https://example.com/beta"

    def test_distributor_fields(self):
        build = BuildFactory()
        db.session.commit()
        sidecar = self._make_sidecar()
        sidecar["info"]["distributor"] = "Test Distributor"
        sidecar["info"]["distributor_url"] = "https://dist.example.com"
        apply_sidecar_to_db(db.session, build, sidecar)
        db.session.expire_all()
        refreshed = db.session.get(Build, build.id)
        assert refreshed.version.distributor == "Test Distributor"
        assert refreshed.version.distributor_url == "https://dist.example.com"

    def test_flush_within_session(self):
        build = BuildFactory(changelog=None)
        db.session.commit()
        assert build.changelog is None
        apply_sidecar_to_db(db.session, build, self._make_sidecar())
        assert build.changelog == "Initial release"
        assert build.signed is True
