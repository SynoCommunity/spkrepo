# -*- coding: utf-8 -*-
import hashlib
import json
from datetime import datetime, timedelta
from unittest import TestLoader, TestSuite

from flask import url_for

from spkrepo.ext import db
from spkrepo.models import Architecture, Download, Firmware
from spkrepo.tests.common import (
    BaseTestCase,
    BuildFactory,
    DownloadFactory,
    PackageFactory,
)


class CatalogTestCase(BaseTestCase):
    def assertCatalogEntry(self, entry, build, data=None, link_params=None):
        data = data or {}
        link_params = link_params or {}

        # mandatory
        self.assertEqual(entry["package"], build.version.package.name)
        self.assertEqual(entry["version"], build.version.version_string)
        self.assertEqual(
            entry["dname"],
            build.version.displaynames[data.get("language", "enu")].displayname,
        )
        self.assertEqual(
            entry["desc"],
            build.version.descriptions[data.get("language", "enu")].description,
        )
        self.assertGreaterEqual(len(entry["thumbnail"]), 1)
        self.assertEqual(
            entry["thumbnail"],
            [
                url_for("nas.data", path=i.path, _external=True)
                for i in build.version.icons.values()
            ],
        )
        for t in entry["thumbnail"]:
            self.assert200(self.client.get(t))
        self.assertEqual(
            entry["qinst"],
            build.version.license is None and build.version.install_wizard is False,
        )
        self.assertEqual(
            entry["qupgrade"],
            build.version.license is None and build.version.upgrade_wizard is False,
        )
        self.assertEqual(
            entry["qstart"],
            (
                build.version.license is None
                and build.version.install_wizard is False
                and build.version.startable is not False
            ),
        )
        self.assertEqual(entry["deppkgs"], build.version.dependencies)
        self.assertEqual(entry["conflictpkgs"], build.version.conflicts)

        # download
        download_response = self.client.get(
            entry["link"],
            follow_redirects=True,
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        )
        self.assert200(download_response)

        # md5
        if build.md5:
            self.assertEqual(entry["md5"], build.md5)
            self.assertEqual(
                entry["md5"], hashlib.md5(download_response.data).hexdigest()
            )

        # screenshots
        if build.version.package.screenshots:
            self.assertEqual(
                entry["snapshot"],
                [
                    url_for("nas.data", path=s.path, _external=True)
                    for s in build.version.package.screenshots
                ],
            )
            for s in build.version.package.screenshots:
                self.assert200(
                    self.client.get(
                        url_for("nas.data", path=s.path), follow_redirects=True
                    )
                )
        else:
            self.assertNotIn("snapshot", entry)

        # report_url
        if build.version.report_url:
            entry["report_url"] = build.version.report_url
            entry["beta"] = True
        else:
            self.assertNotIn("report_url", entry)
            self.assertNotIn("beta", entry)

        # changelog
        if build.version.changelog:
            self.assertEqual(entry["changelog"], build.version.changelog)
        else:
            self.assertNotIn("changelog", entry)

        # distributor
        if build.version.distributor:
            self.assertEqual(entry["distributor"], build.version.distributor)
        else:
            self.assertNotIn("distributor", entry)

        # distributor_url
        if build.version.distributor_url:
            self.assertEqual(entry["distributor_url"], build.version.distributor_url)
        else:
            self.assertNotIn("distributor_url", entry)

        # maintainer
        if build.version.maintainer:
            self.assertEqual(entry["maintainer"], build.version.maintainer)
        else:
            self.assertNotIn("maintainer", entry)

        # maintainer_url
        if build.version.maintainer_url:
            self.assertEqual(entry["maintainer_url"], build.version.maintainer_url)
        else:
            self.assertNotIn("maintainer_url", entry)

        # depsers
        if build.version.service_dependencies:
            self.assertEqual(
                entry["depsers"],
                " ".join([s.code for s in build.version.service_dependencies]),
            )
        else:
            self.assertNotIn("depsers", entry)

        # conf_deppkgs
        if build.version.conf_dependencies:
            self.assertEqual(entry["conf_deppkgs"], build.version.conf_dependencies)
        else:
            self.assertNotIn("conf_deppkgs", entry)

        # conf_conxpkgs
        if build.version.conf_conflicts:
            self.assertEqual(entry["conf_conxpkgs"], build.version.conf_conflicts)
        else:
            self.assertNotIn("conf_conxpkgs", entry)

        # conf_privilege
        if build.version.conf_privilege:
            self.assertEqual(entry["conf_privilege"], build.version.conf_privilege)
        else:
            self.assertNotIn("conf_privilege", entry)

        # conf_resource
        if build.version.conf_resource:
            self.assertEqual(entry["conf_resource"], build.version.conf_resource)
        else:
            self.assertNotIn("conf_resource", entry)

    def test_missing_data_arch(self):
        self.assert400(
            self.client.post(
                url_for("nas.catalog"), data=dict(build="1594", language="enu")
            )
        )

    def test_missing_data_build(self):
        self.assert400(
            self.client.post(
                url_for("nas.catalog"), data=dict(arch="88f6281", language="enu")
            )
        )

    def test_missing_data_language(self):
        self.assert400(
            self.client.post(
                url_for("nas.catalog"), data=dict(arch="88f6281", build="1594")
            )
        )

    def test_wrong_data_arch(self):
        self.assert422(
            self.client.post(
                url_for("nas.catalog"),
                data=dict(arch="zzzzzzz", build="1594", language="enu"),
            )
        )

    def test_wrong_data_build(self):
        self.assert422(
            self.client.post(
                url_for("nas.catalog"),
                data=dict(arch="88f6281", build="zzzz", language="enu"),
            )
        )

    def test_wrong_data_language(self):
        self.assert422(
            self.client.post(
                url_for("nas.catalog"),
                data=dict(arch="88f6281", build="1594", language="zzz"),
            )
        )

    def test_stable_build_active_stable(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertCatalogEntry(
            catalog[0], build, data, dict(arch="88f628x", build="1594")
        )

    def test_stable_build_active_stable_5004(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="5004", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertIn("packages", catalog)
        self.assertIn("keyrings", catalog)
        self.assertEqual(len(catalog["packages"]), 1)
        self.assertCatalogEntry(
            catalog["packages"][0], build, data, dict(arch="88f628x", build="5004")
        )

    def test_stable_build_active_stable_download_count(self):
        package = PackageFactory()
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__package=package,
            architectures=[Architecture.find("cedarview")],
            firmware=Firmware.find(1594),
        )
        DownloadFactory.create_batch(1, build=build, date=datetime.now())
        DownloadFactory.create_batch(
            2, build=build, date=datetime.now() - timedelta(days=30)
        )
        DownloadFactory.create_batch(
            4, build=build, date=datetime.now() - timedelta(days=100)
        )
        db.session.commit()
        data = dict(arch="cedarview", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertEqual(catalog[0]["download_count"], 7)
        self.assertEqual(catalog[0]["recent_download_count"], 3)

    def test_stable_build_active_stable_null_data(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__changelog=None,
            version__distributor=None,
            version__distributor_url=None,
            version__maintainer=None,
            version__maintainer_url=None,
            version__service_dependencies=[],
            version__dependencies=None,
            version__conflicts=None,
            version__package__add_screenshot=False,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertCatalogEntry(
            catalog[0], build, data, dict(arch="88f628x", build="1594")
        )

    def test_stable_build_active_stable_no_distributor(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__distributor=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertCatalogEntry(
            catalog[0], build, data, dict(arch="88f628x", build="1594")
        )

    def test_stable_build_active_stable_qinst(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__license=None,
            version__install_wizard=False,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertCatalogEntry(
            catalog[0], build, data, dict(arch="88f628x", build="1594")
        )

    def test_stable_build_active_stable_qstart(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__license=None,
            version__install_wizard=False,
            version__startable=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertCatalogEntry(
            catalog[0], build, data, dict(arch="88f628x", build="1594")
        )

    def test_stable_build_active_stable_qstart_startable(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__license=None,
            version__install_wizard=False,
            version__startable=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertCatalogEntry(
            catalog[0], build, data, dict(arch="88f628x", build="1594")
        )

    def test_stable_build_active_stable_different_arch(self):
        BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("cedarview")],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 0)

    def test_stable_build_active_stable_different_firmware(self):
        BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(4458),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 0)

    def test_stable_build_not_active_stable(self):
        BuildFactory(
            active=False,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 0)

    def test_stable_build_active_not_stable(self):
        BuildFactory(
            active=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 0)

    def test_not_stable_build_active_stable(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertCatalogEntry(
            catalog[0], build, data, dict(arch="88f628x", build="1594")
        )

    def test_not_stable_build_active_not_stable(self):
        build = BuildFactory(
            active=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 1)
        self.assertCatalogEntry(
            catalog[0], build, data, dict(arch="88f628x", build="1594")
        )

    def test_not_stable_build_not_active_stable(self):
        BuildFactory(
            active=False,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 0)

    def test_not_stable_build_not_active_not_stable(self):
        BuildFactory(
            active=False,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 0)

    def test_stable_build_not_active_not_stable(self):
        BuildFactory(
            active=False,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode(response.charset))
        self.assertEqual(len(catalog), 0)


class DownloadTestCase(BaseTestCase):
    def test_generic(self):
        architecture = Architecture.find("88f6281", syno=True)
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[architecture],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        self.assertEqual(Download.query.count(), 0)
        response = self.client.get(
            url_for(
                "nas.download",
                architecture_id=architecture.id,
                firmware_build=4458,
                build_id=build.id,
            ),
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
            headers={"User-Agent": "My User Agent"},
        )
        self.assert302(response)
        self.assertEqual(Download.query.count(), 1)
        download = Download.query.first()
        self.assertEqual(download.ip_address, "127.0.0.1")
        self.assertEqual(download.user_agent, "My User Agent")
        self.assertEqual(download.firmware_build, 4458)
        self.assertAlmostEqual(
            download.date,
            datetime.utcnow().replace(microsecond=0),
            delta=timedelta(seconds=10),
        )

    def test_wrong_build(self):
        architecture = Architecture.find("88f6281", syno=True)
        build = BuildFactory(
            active=False,
            version__report_url=None,
            architectures=[architecture],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        self.assertEqual(Download.query.count(), 0)
        response = self.client.get(
            url_for(
                "nas.download",
                architecture_id=architecture.id,
                firmware_build=4458,
                build_id=build.id + 1,
            )
        )
        self.assert404(response)
        self.assertEqual(Download.query.count(), 0)

    def test_inactive_build(self):
        architecture = Architecture.find("88f6281", syno=True)
        build = BuildFactory(
            active=False,
            version__report_url=None,
            architectures=[architecture],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        self.assertEqual(Download.query.count(), 0)
        response = self.client.get(
            url_for(
                "nas.download",
                architecture_id=architecture.id,
                firmware_build=4458,
                build_id=build.id,
            )
        )
        self.assert403(response)
        self.assertEqual(Download.query.count(), 0)

    def test_wrong_architecture(self):
        architecture = Architecture.find("88f6281", syno=True)
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[architecture],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        self.assertEqual(Download.query.count(), 0)
        response = self.client.get(
            url_for(
                "nas.download",
                architecture_id=10,
                firmware_build=4458,
                build_id=build.id,
            )
        )
        self.assert404(response)
        self.assertEqual(Download.query.count(), 0)

    def test_incorrect_architecture(self):
        architecture = Architecture.find("88f6281", syno=True)
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[architecture],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        self.assertEqual(Download.query.count(), 0)
        response = self.client.get(
            url_for(
                "nas.download",
                architecture_id=Architecture.find("cedarview").id,
                firmware_build=4458,
                build_id=build.id,
            )
        )
        self.assert400(response)
        self.assertEqual(Download.query.count(), 0)

    def test_incorrect_firmware_build(self):
        architecture = Architecture.find("88f6281", syno=True)
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[architecture],
            firmware=Firmware.find(1594),
        )
        db.session.commit()
        self.assertEqual(Download.query.count(), 0)
        response = self.client.get(
            url_for(
                "nas.download",
                architecture_id=architecture.id,
                firmware_build=1593,
                build_id=build.id,
            )
        )
        self.assert400(response)
        self.assertEqual(Download.query.count(), 0)


def suite():
    suite = TestSuite()
    suite.addTest(TestLoader().loadTestsFromTestCase(CatalogTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(DownloadTestCase))
    return suite
