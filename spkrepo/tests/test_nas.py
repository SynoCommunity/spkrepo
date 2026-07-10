# -*- coding: utf-8 -*-
import hashlib
import json
from datetime import datetime, timedelta

from flask import url_for

from spkrepo.ext import db
from spkrepo.models import Architecture, DownloadStat, Firmware, PackageDownloadCounts
from spkrepo.tests.common import (
    BaseTestCase,
    BuildFactory,
    DownloadStatFactory,
    PackageFactory,
    VersionFactory,
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
            build.descriptions[data.get("language", "enu")].description,
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
        if build.changelog:
            self.assertEqual(entry["changelog"], build.changelog)
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

    def test_catalog_validation(self):
        cases = [
            (dict(build="1594", language="enu"), 400),
            (dict(arch="88f6281", language="enu"), 400),
            (dict(arch="88f6281", build="1594"), 400),
            (dict(arch="zzzzzzz", build="1594", language="enu"), 422),
            (dict(arch="88f6281", build="zzzz", language="enu"), 422),
            (dict(arch="88f6281", build="1594", language="zzz"), 422),
            (dict(arch="88f6281", build="1594", language="enu", major="abc"), 422),
        ]
        for data, status in cases:
            with self.subTest(data=data, status=status):
                getattr(self, f"assert{status}")(
                    self.client.post(url_for("nas.catalog"), data=data)
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

    def _assert_dsm6_catalog(self, arch_name):
        build = BuildFactory(
            active=True,
            version__report_url=None,
            architectures=[Architecture.find(arch_name, syno=True)],
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

    def test_stable_noarch_build_active_stable_dsm6(self):
        self._assert_dsm6_catalog("noarch")

    def test_stable_arch_build_active_stable_dsm6(self):
        self._assert_dsm6_catalog("88f6281")

    def test_stable_build_active_stable_download_count(self):
        package = PackageFactory()
        build = BuildFactory(
            active=True,
            version__report_url=None,
            version__package=package,
            architectures=[Architecture.find("cedarview")],
            firmware_min=Firmware.find(1594),
        )
        DownloadStatFactory(
            package=package,
            build=build,
            date=datetime.now().date(),
            count=1,
        )
        DownloadStatFactory(
            package=package,
            build=build,
            date=(datetime.now() - timedelta(days=30)).date(),
            count=2,
        )
        DownloadStatFactory(
            package=package,
            build=build,
            date=(datetime.now() - timedelta(days=100)).date(),
            count=4,
        )
        db.session.commit()

        # Populate the package_download_counts materialized view used by
        # the catalog, matching what the production Celery task does.
        ninety_days_ago = datetime.now().date() - timedelta(days=90)
        total = db.session.scalar(
            db.select(db.func.coalesce(db.func.sum(DownloadStat.count), 0)).filter(
                DownloadStat.package_id == package.id
            )
        )
        recent = db.session.scalar(
            db.select(db.func.coalesce(db.func.sum(DownloadStat.count), 0)).filter(
                DownloadStat.package_id == package.id,
                DownloadStat.date >= ninety_days_ago,
            )
        )
        db.session.add(
            PackageDownloadCounts(
                package_id=package.id,
                download_count=total,
                recent_download_count=recent,
            )
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
            changelog=None,
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

    def _catalog_post(self, data):
        response = self.client.post(url_for("nas.catalog"), data=data)
        self.assert200(response)
        self.assertHeader(response, "Content-Type", "application/json")
        catalog = json.loads(response.data.decode())
        return catalog["packages"] if isinstance(catalog, dict) else catalog

    def test_stable_channel_excludes_inactive_stable_build(self):
        BuildFactory(
            active=False,
            version__report_url=None,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        packages = self._catalog_post(
            dict(arch="88f6281", build="1594", language="enu")
        )
        self.assertEqual(len(packages), 0)

    def test_stable_channel_excludes_active_beta_build(self):
        BuildFactory(
            active=True,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        packages = self._catalog_post(
            dict(arch="88f6281", build="1594", language="enu")
        )
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
        packages = self._catalog_post(data)
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
        packages = self._catalog_post(data)
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
        packages = self._catalog_post(data)
        self.assertEqual(len(packages), 0)

    def test_inactive_beta_build_excluded_from_beta_channel(self):
        BuildFactory(
            active=False,
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()
        data = dict(
            arch="88f6281", build="1594", language="enu", package_update_channel="beta"
        )
        packages = self._catalog_post(data)
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

    def test_catalog_returns_per_build_fields(self):
        version = VersionFactory(report_url=None)
        db.session.commit()

        build_a = BuildFactory.create(
            version=version,
            active=True,
            changelog="changelog_A",
            architectures=[Architecture.find("88f6281", syno=True)],
            firmware_min=Firmware.find(1594),
            buildmanifest={"dependencies": "dep_A", "conflicts": "con_A"},
        )
        build_a.descriptions["enu"].description = "Desc A"

        build_b = BuildFactory.create(
            version=version,
            active=True,
            changelog="changelog_B",
            architectures=[Architecture.find("cedarview", syno=True)],
            firmware_min=Firmware.find(23739),
            buildmanifest={"dependencies": "dep_B", "conflicts": "con_B"},
        )
        build_b.descriptions["enu"].description = "Desc B"
        db.session.commit()

        # Query matching build_a
        data_a = dict(arch="88f6281", build="1594", language="enu")
        response_a = self.client.post(url_for("nas.catalog"), data=data_a)
        self.assert200(response_a)
        catalog_a = json.loads(response_a.data.decode())
        packages_a = catalog_a["packages"] if isinstance(catalog_a, dict) else catalog_a
        self.assertEqual(len(packages_a), 1)
        self.assertEqual(packages_a[0]["changelog"], "changelog_A")
        self.assertEqual(packages_a[0]["desc"], "Desc A")
        self.assertEqual(packages_a[0]["deppkgs"], "dep_A")
        self.assertEqual(packages_a[0]["conflictpkgs"], "con_A")

        # Query matching build_b
        data_b = dict(arch="cedarview", build="23739", language="enu")
        response_b = self.client.post(url_for("nas.catalog"), data=data_b)
        self.assert200(response_b)
        catalog_b = json.loads(response_b.data.decode())
        packages_b = catalog_b["packages"] if isinstance(catalog_b, dict) else catalog_b
        self.assertEqual(len(packages_b), 1)
        self.assertEqual(packages_b[0]["changelog"], "changelog_B")
        self.assertEqual(packages_b[0]["desc"], "Desc B")
        self.assertEqual(packages_b[0]["deppkgs"], "dep_B")
        self.assertEqual(packages_b[0]["conflictpkgs"], "con_B")

        # Build-level auto-generated fields (md5, link) should differ per build
        self.assertNotEqual(packages_a[0]["md5"], packages_b[0]["md5"])
        self.assertNotEqual(packages_a[0]["link"], packages_b[0]["link"])
