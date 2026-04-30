# -*- coding: utf-8 -*-
import hashlib
import json
from datetime import datetime, timedelta, timezone

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
    def assertCatalogEntry(self, entry, build, data=None):
        data = data or {}

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
        self.assertEqual(entry["deppkgs"], build.buildmanifest.dependencies)
        self.assertEqual(entry["conflictpkgs"], build.buildmanifest.conflicts)

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
        self.assertIn("snapshot", entry)
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
            self.assertEqual(entry["snapshot"], [])

        # report_url / beta
        if build.version.report_url:
            self.assertEqual(entry["report_url"], build.version.report_url)
            self.assertTrue(entry.get("beta"))
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

        # size
        if build.size:
            self.assertEqual(entry["size"], build.size)
        else:
            self.assertNotIn("size", entry)

        # startable
        if build.version.startable is not None:
            self.assertEqual(
                entry["startable"], "yes" if build.version.startable else "no"
            )
        else:
            self.assertNotIn("startable", entry)

        # download counts — always present, values verified separately
        self.assertIn("download_count", entry)
        self.assertIn("recent_download_count", entry)
        self.assertIsInstance(entry["download_count"], int)
        self.assertIsInstance(entry["recent_download_count"], int)

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
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        # DSM 3.x (build < 5004) returns a bare JSON list, not a dict
        self.assertIsInstance(catalog, list)
        packages = catalog
        self.assertEqual(len(packages), 1)
        self.assertCatalogEntry(packages[0], build, data)

    def test_stable_noarch_build_active_stable_dsm6(self):
        # DSM 6.2 (build 23739): response format includes packages + keyrings
        # (build >= 5004, < 40000). firmware_min must also be DSM 6.x so the
        # major filter (startswith("6.")) matches.
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("noarch", syno=True)],
            firmware_min=Firmware.find(23739),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="23739", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        self.assertIn("packages", catalog)
        self.assertIn("keyrings", catalog)
        self.assertEqual(len(catalog["packages"]), 1)
        self.assertCatalogEntry(catalog["packages"][0], build, data)

    def test_stable_arch_build_active_stable_dsm6(self):
        # DSM 6.2 arch package appears in a DSM 6 query; response includes keyrings.
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(23739),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="23739", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        self.assertIn("packages", catalog)
        self.assertIn("keyrings", catalog)
        self.assertEqual(len(catalog["packages"]), 1)
        self.assertCatalogEntry(catalog["packages"][0], build, data)

    def test_stable_build_active_stable_download_count(self):
        package = PackageFactory()
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__package=package,
            architectures=[Architecture.find("cedarview")],
            firmware_min=Firmware.find(1594),
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
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]["download_count"], 7)
        self.assertEqual(packages[0]["recent_download_count"], 3)

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
            buildmanifest__dependencies=None,
            buildmanifest__conflicts=None,
            version__package__add_screenshot=False,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 1)
        self.assertCatalogEntry(packages[0], build, data)

    def test_stable_build_active_stable_quick_flags_all_true(self):
        # qinst=True, qupgrade=True, qstart=True:
        # license=None, no wizards, startable=True.
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__license=None,
            version__install_wizard=False,
            version__startable=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 1)
        entry = packages[0]
        self.assertTrue(entry["qinst"])
        self.assertTrue(entry["qupgrade"])
        self.assertTrue(entry["qstart"])
        self.assertCatalogEntry(entry, build, data)

    def test_stable_build_active_stable_qstart_false_when_not_startable(self):
        # qstart=False when startable=False,
        # even with license=None and no install wizard.
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__license=None,
            version__install_wizard=False,
            version__startable=False,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 1)
        entry = packages[0]
        self.assertTrue(entry["qinst"])
        self.assertTrue(entry["qupgrade"])
        self.assertFalse(entry["qstart"])
        self.assertCatalogEntry(entry, build, data)

    def test_stable_build_active_stable_different_arch(self):
        BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("cedarview")],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 0)

    def test_stable_build_active_stable_different_firmware(self):
        BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(4458),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 0)

    def test_stable_channel_excludes_inactive_stable_build(self):
        BuildFactory(
            active=False,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 0)

    def test_stable_channel_excludes_active_beta_build(self):
        BuildFactory(
            active=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="1594", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 0)

    def test_beta_channel_includes_active_stable_build(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 1)
        self.assertCatalogEntry(packages[0], build, data)

    def test_beta_channel_includes_active_beta_build(self):
        build = BuildFactory(
            active=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 1)
        self.assertCatalogEntry(packages[0], build, data)

    def test_inactive_stable_build_excluded_from_beta_channel(self):
        BuildFactory(
            active=False,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 0)

    def test_inactive_beta_build_excluded_from_beta_channel(self):
        # An inactive beta build must not appear even in the beta channel.
        BuildFactory(
            active=False,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 0)

    def test_response_format_dsm7_no_keyrings(self):
        # DSM 7 (build >= 40000): response is {"packages": [...]} with NO keyrings key.
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(42661),
        )
        db.session.commit()
        data = dict(arch="88f6281", build="42661", language="enu")
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        self.assertIn("packages", catalog)
        self.assertNotIn("keyrings", catalog)
        self.assertEqual(len(catalog["packages"]), 1)
        self.assertCatalogEntry(catalog["packages"][0], build, data)

    def test_beta_package_excluded_for_dsm7(self):
        BuildFactory(
            active=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(42661),
        )
        db.session.commit()
        data = dict(
            arch="88f6281",
            build="42661",
            language="enu",
            package_update_channel="beta",
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 0)

    def test_stable_package_included_for_dsm7_beta_channel(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(42661),
        )
        db.session.commit()
        data = dict(
            arch="88f6281",
            build="42661",
            language="enu",
            package_update_channel="beta",
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 1)
        self.assertEqual(packages[0]["package"], build.version.package.name)

    def test_explicit_major_parameter_overrides_firmware_table(self):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(4458),
        )
        db.session.commit()
        # Without override: build=23739 → major=6,
        # package has firmware_min DSM 5 → excluded.
        data_auto = dict(arch="88f6281", build="23739", language="enu")
        response_auto = self.client.post(url_for("nas.catalog"), data=data_auto)
        self.assert200(response_auto)
        catalog_auto = json.loads(response_auto.data.decode())
        packages_auto = (
            catalog_auto["packages"] if isinstance(catalog_auto, dict) else catalog_auto
        )
        self.assertEqual(len(packages_auto), 0)
        # With explicit major=5: overrides the table lookup, package is now included.
        data_explicit = dict(arch="88f6281", build="23739", language="enu", major="5")
        response_explicit = self.client.post(url_for("nas.catalog"), data=data_explicit)
        self.assert200(response_explicit)
        catalog_explicit = json.loads(response_explicit.data.decode())
        packages_explicit = (
            catalog_explicit["packages"]
            if isinstance(catalog_explicit, dict)
            else catalog_explicit
        )
        self.assertEqual(len(packages_explicit), 1)
        self.assertEqual(packages_explicit[0]["package"], build.version.package.name)

    def test_invalid_major_parameter_returns_422(self):
        self.assert422(
            self.client.post(
                url_for("nas.catalog"),
                data=dict(arch="88f6281", build="1594", language="enu", major="abc"),
            )
        )

    def test_beta_build_fields_present_in_entry(self):
        build = BuildFactory(
            active=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        # Ensure report_url is set so the build is treated as beta
        self.assertIsNotNone(build.version.report_url)
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        catalog = json.loads(response.data.decode())
        packages = catalog["packages"] if isinstance(catalog, dict) else catalog
        self.assertEqual(len(packages), 1)
        entry = packages[0]
        self.assertIn("report_url", entry)
        self.assertEqual(entry["report_url"], build.version.report_url)
        self.assertIn("beta", entry)
        self.assertTrue(entry["beta"])


class DownloadTestCase(BaseTestCase):
    def test_generic(self):
        architecture = Architecture.find("88f6281", syno=True)
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[architecture],
            firmware_min=Firmware.find(1594),
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
            datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None),
            delta=timedelta(seconds=10),
        )

    def test_wrong_build(self):
        architecture = Architecture.find("88f6281", syno=True)
        build = BuildFactory(
            active=False,
            version__report_url=None,
            architectures=[architecture],
            firmware_min=Firmware.find(1594),
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
            firmware_min=Firmware.find(1594),
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
            firmware_min=Firmware.find(1594),
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
            firmware_min=Firmware.find(1594),
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
            firmware_min=Firmware.find(1594),
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

    def test_firmware_build_above_firmware_max(self):
        architecture = Architecture.find("88f6281", syno=True)
        firmware_min = Firmware.find(1594)
        firmware_max = Firmware.find(4458)
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[architecture],
            firmware_min=firmware_min,
            firmware_max=firmware_max,
        )
        db.session.commit()
        self.assertEqual(Download.query.count(), 0)
        response = self.client.get(
            url_for(
                "nas.download",
                architecture_id=architecture.id,
                firmware_build=firmware_max.build + 1,
                build_id=build.id,
            )
        )
        self.assert400(response)
        self.assertEqual(Download.query.count(), 0)
