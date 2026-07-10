# -*- coding: utf-8 -*-
import io
import json
import tarfile

from mock import Mock

from spkrepo.exceptions import SPKParseError
from spkrepo.ext import db
from spkrepo.models import Architecture, Package
from spkrepo.tests.common import (
    BaseTestCase,
    BuildFactory,
    PackageFactory,
    create_info,
    create_spk,
)
from spkrepo.utils import (
    SPK,
    assert_version_metadata_matches_db,
    extract_version_metadata,
)


class SPKParseTestCase(BaseTestCase):
    def test_generic(self):
        architectures = db.session.execute(db.select(Architecture)).scalars().all()
        build = BuildFactory.build(
            version__upgrade_wizard=True,
            architectures=[architectures[0], architectures[1]],
        )
        with create_spk(build, signature="signature") as f:
            spk = SPK(f)

        # info
        info_keys = [
            "arch",
            "changelog",
            "description",
            "description_enu",
            "displayname",
            "displayname_enu",
            "distributor",
            "distributor_url",
            "firmware",
            "install_conflict_packages",
            "install_dep_packages",
            "install_dep_services",
            "maintainer",
            "maintainer_url",
            "package",
            "report_url",
            "support_conf_folder",
            "version",
        ]
        self.assertEqual(set(info_keys), set(spk.info.keys()))
        self.assertEqual(
            {Architecture.from_syno.get(a, a) for a in spk.info["arch"].split()},
            {a.code for a in build.architectures},
        )
        self.assertEqual(build.changelog, spk.info["changelog"])
        self.assertEqual(build.descriptions["enu"].description, spk.info["description"])
        self.assertEqual(
            build.descriptions["enu"].description, spk.info["description_enu"]
        )
        self.assertEqual(
            build.version.displaynames["enu"].displayname, spk.info["displayname"]
        )
        self.assertEqual(
            build.version.displaynames["enu"].displayname, spk.info["displayname_enu"]
        )
        self.assertEqual(build.version.distributor, spk.info["distributor"])
        self.assertEqual(build.version.distributor_url, spk.info["distributor_url"])
        self.assertEqual(build.firmware_min.firmware_string, spk.info["firmware"])
        self.assertEqual(
            build.buildmanifest.conflicts, spk.info["install_conflict_packages"]
        )
        self.assertEqual(
            build.buildmanifest.dependencies, spk.info["install_dep_packages"]
        )
        self.assertEqual(
            " ".join(s.code for s in build.version.service_dependencies),
            spk.info["install_dep_services"],
        )
        self.assertEqual(build.version.maintainer, spk.info["maintainer"])
        self.assertEqual(build.version.maintainer_url, spk.info["maintainer_url"])
        self.assertEqual(build.version.package.name, spk.info["package"])
        self.assertEqual(build.version.report_url, spk.info["report_url"])
        self.assertEqual(
            (
                build.buildmanifest.conf_dependencies is not None
                or build.buildmanifest.conf_conflicts is not None
                or build.buildmanifest.conf_privilege is not None
                or build.buildmanifest.conf_resource is not None
            ),
            spk.info["support_conf_folder"],
        )
        self.assertEqual(build.version.version_string, spk.info["version"])

        # icons
        self.assertEqual(set(build.version.icons.keys()), set(spk.icons.keys()))

        # wizards
        if not build.version.install_wizard:
            self.assertNotIn("install", spk.wizards)
        else:
            self.assertIn("install", spk.wizards)
        if not build.version.upgrade_wizard:
            self.assertNotIn("upgrade", spk.wizards)
        else:
            self.assertIn("upgrade", spk.wizards)

        # license
        self.assertEqual(build.version.license, spk.license)

        # signature
        self.assertEqual("signature", spk.signature)

    def test_info_blank_like(self):
        build = BuildFactory.build()
        info = io.BytesIO(
            "\n".join([f'{k}="{v}"\n' for k, v in create_info(build).items()]).encode(
                "utf-8"
            )
        )
        with create_spk(build, info=info) as f:
            SPK(f)

    def test_info_boolean(self):
        for startable, expected in [(True, True), (False, False)]:
            with self.subTest(startable=startable, expected=expected):
                build = BuildFactory.build(version__startable=startable)
                with create_spk(build) as f:
                    self.assertEqual(SPK(f).info["startable"], expected)

    def test_no_info(self):
        build = BuildFactory.build()
        with create_spk(build, with_info=False) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Missing INFO file", str(cm.exception))

    def test_no_package_tgz(self):
        build = BuildFactory.build()
        with create_spk(build, with_package=False) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Missing package.tgz file", str(cm.exception))

    def test_wrong_license_encoding(self):
        build = BuildFactory.build(version__license="License française")
        with create_spk(build, license_encoding="latin-1") as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Wrong LICENSE encoding", str(cm.exception))

    def test_wrong_syno_signature_encoding(self):
        build = BuildFactory.build()
        with create_spk(
            build, signature="Signature française", signature_encoding="latin-1"
        ) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Wrong syno_signature.asc encoding", str(cm.exception))

    def test_wrong_info_encoding(self):
        build = BuildFactory.build()
        info = create_info(build)
        info["description"] = "Description en français"
        with create_spk(build, info=info, info_encoding="latin-1") as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Wrong INFO encoding", str(cm.exception))

    def test_invalid_info(self):
        build = BuildFactory.build()
        info = io.BytesIO(
            "\n".join([f"{k}={v}" for k, v in create_info(build).items()]).encode(
                "utf-8"
            )
        )
        with create_spk(build, info=info) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Invalid INFO", str(cm.exception))

    def test_invalid_info_icon(self):
        build = BuildFactory.build()
        info = create_info(build)
        info["package_icon_120"] = "package_icon_120"
        with create_spk(build, info=info) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Invalid INFO icon: package_icon_120", str(cm.exception))

    def test_invalid_info_boolean_startable(self):
        build = BuildFactory.build()
        info = create_info(build)
        info["startable"] = "Something"
        with create_spk(build, info=info) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Invalid INFO boolean: startable", str(cm.exception))

    def test_invalid_info_package(self):
        build = BuildFactory.build(version__package__name="Invalid package name")
        with create_spk(build) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Invalid INFO package", str(cm.exception))

    def test_missing_info_package(self):
        build = BuildFactory.build()
        info = create_info(build)
        del info["package"]
        with create_spk(build, info=info) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Missing INFO: package", str(cm.exception))

    def test_checksum_mismatch(self):
        build = BuildFactory.build()
        info = create_info(build)
        info["checksum"] = "checksum"
        with create_spk(build, info=info) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Checksum mismatch", str(cm.exception))

    def test_missing_72px_icon(self):
        build = BuildFactory.build(version__add_icon=False)
        with create_spk(build) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Missing 72px icon", str(cm.exception))

    def test_invalid_spk(self):
        build = BuildFactory.build()
        with create_spk(build) as f:
            f.seek(50)
            invalid_spk = io.BytesIO(f.read())
        with self.assertRaises(SPKParseError) as cm:
            SPK(invalid_spk)
        self.assertEqual("Invalid SPK", str(cm.exception))

    def test_missing_conf_folder(self):
        build = BuildFactory.build(
            buildmanifest__conf_dependencies=None,
            buildmanifest__conf_conflicts=None,
            buildmanifest__conf_privilege=None,
            buildmanifest__conf_resource=None,
        )
        info = create_info(build)
        info["support_conf_folder"] = "yes"
        with create_spk(build, info=info, with_conf=False) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Missing conf folder", str(cm.exception))

    def test_wrong_conf_dependencies_encoding(self):
        build = BuildFactory.build(
            buildmanifest__conf_dependencies=json.dumps(
                {"déçu": {"dsm_min_ver": "5.0-4300"}}
            )
        )
        with create_spk(build, conf_dependencies_encoding="latin-1") as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Wrong conf/PKG_DEPS encoding", str(cm.exception))

    def test_wrong_conf_conflicts_encoding(self):
        build = BuildFactory.build(
            buildmanifest__conf_conflicts=json.dumps(
                {"déçu": {"dsm_min_ver": "5.0-4300"}}
            )
        )
        with create_spk(build, conf_conflicts_encoding="latin-1") as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Wrong conf/PKG_CONX encoding", str(cm.exception))

    def test_wrong_conf_privilege_encoding(self):
        build = BuildFactory.build(
            buildmanifest__conf_privilege=json.dumps(
                {"déçu": {"run-as": "<run-as>"}}, ensure_ascii=False
            )
        )
        with create_spk(build, conf_privilege_encoding="latin-1") as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Wrong conf/privilege encoding", str(cm.exception))

    def test_wrong_conf_resource_encoding(self):
        build = BuildFactory.build(
            buildmanifest__conf_resource=json.dumps(
                {"déçu": {"<resource-id>": "<specification>"}}, ensure_ascii=False
            )
        )
        with create_spk(build, conf_resource_encoding="latin-1") as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Wrong conf/resource encoding", str(cm.exception))

    def test_post_conf_privilege_invalid_json(self):
        build = BuildFactory.build(buildmanifest__conf_privilege='{"invalid": "json}')
        with create_spk(build) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual(
            "File conf/privilege is not valid JSON",
            str(cm.exception),
        )

    def test_post_conf_resource_invalid_json(self):
        build = BuildFactory.build(buildmanifest__conf_resource='{"invalid": "json}')
        with create_spk(build) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual(
            "File conf/resource is not valid JSON",
            str(cm.exception),
        )

    def test_empty_conf_folder(self):
        build = BuildFactory.build(
            buildmanifest__conf_dependencies=None,
            buildmanifest__conf_conflicts=None,
            buildmanifest__conf_privilege=None,
            buildmanifest__conf_resource=None,
        )
        info = create_info(build)
        info["support_conf_folder"] = "yes"
        with create_spk(build, info=info, with_conf=True) as f:
            with self.assertRaises(SPKParseError) as cm:
                SPK(f)
        self.assertEqual("Empty conf folder", str(cm.exception))


class SPKSignTestCase(BaseTestCase):
    def test_generic(self):
        build = BuildFactory.build(version__upgrade_wizard=True)
        f = create_spk(build)
        spk = SPK(f)
        with tarfile.open(fileobj=f, mode="r:") as tar:
            self.assertNotIn("syno_signature.asc", tar.getnames())
        self.assertIsNone(spk.signature)
        spk._generate_signature = Mock(return_value="timestamped signature")
        spk.sign("timestamp_url", "gnupghome")
        with tarfile.open(fileobj=f, mode="r:") as tar:
            self.assertIn("syno_signature.asc", tar.getnames())
            self.assertEqual(
                tar.extractfile("syno_signature.asc").read(), b"timestamped signature"
            )
        self.assertEqual(spk.signature, "timestamped signature")
        f.close()

    def test_already_signed(self):
        build = BuildFactory.build(version__upgrade_wizard=True)
        with create_spk(build, signature="signature") as f:
            spk = SPK(f)
        spk._generate_signature = Mock(return_value="timestamped signature")
        with self.assertRaises(ValueError) as cm:
            spk.sign("timestamp_url", "gnupghome")
        self.assertEqual("Already signed", str(cm.exception))


class SPKUnsignTestCase(BaseTestCase):
    def test_generic(self):
        build = BuildFactory.build(version__upgrade_wizard=True)
        f = create_spk(build, signature="signature")
        spk = SPK(f)
        spk.unsign()
        with tarfile.open(fileobj=f, mode="r:") as tar:
            self.assertNotIn("syno_signature.asc", tar.getnames())
        f.close()

    def test_not_signed(self):
        build = BuildFactory.build(version__upgrade_wizard=True)
        with create_spk(build) as f:
            spk = SPK(f)
        with self.assertRaises(ValueError) as cm:
            spk.unsign()
        self.assertEqual("Not signed", str(cm.exception))


class ExtractVersionMetadataTestCase(BaseTestCase):
    """Tests for extract_version_metadata — pure dict extraction, no DB writes."""

    def test_displaynames_keyed_by_language_code(self):
        # INFO key "displayname" must map to "enu", not the raw key name.
        build = BuildFactory.build()
        with create_spk(build) as f:
            spk = SPK(f)
        meta = extract_version_metadata(spk)
        self.assertIn("enu", meta["displaynames"])
        self.assertNotIn("displayname", meta["displaynames"])
        self.assertEqual(
            meta["displaynames"]["enu"],
            build.version.displaynames["enu"].displayname,
        )

    def test_startable_defaults_true(self):
        build = BuildFactory.build(version__startable=None)
        with create_spk(build) as f:
            spk = SPK(f)
        meta = extract_version_metadata(spk)
        self.assertTrue(meta["startable"])

    def test_startable_false_when_ctl_stop_false(self):
        build = BuildFactory.build(version__startable=False)
        with create_spk(build) as f:
            spk = SPK(f)
        meta = extract_version_metadata(spk)
        self.assertFalse(meta["startable"])

    def test_install_dep_services_as_set(self):
        build = BuildFactory.build()
        with create_spk(build) as f:
            spk = SPK(f)
        meta = extract_version_metadata(spk)
        expected = {s.code for s in build.version.service_dependencies}
        self.assertEqual(meta["install_dep_services"], expected)

    def test_no_services_returns_empty_set(self):
        build = BuildFactory.build(version__service_dependencies=[])
        with create_spk(build) as f:
            spk = SPK(f)
        meta = extract_version_metadata(spk)
        self.assertEqual(meta["install_dep_services"], set())

    def test_upstream_version_extracted(self):
        build = BuildFactory.build(version__upstream_version="1.2.3")
        with create_spk(build) as f:
            spk = SPK(f)
        meta = extract_version_metadata(spk)
        self.assertEqual(meta["upstream_version"], "1.2.3")

    def test_install_wizard_reflected(self):
        build = BuildFactory.build(version__install_wizard=True)
        with create_spk(build) as f:
            spk = SPK(f)
        meta = extract_version_metadata(spk)
        self.assertTrue(meta["install_wizard"])

    def test_upgrade_wizard_reflected(self):
        build = BuildFactory.build(version__upgrade_wizard=True)
        with create_spk(build) as f:
            spk = SPK(f)
        meta = extract_version_metadata(spk)
        self.assertTrue(meta["upgrade_wizard"])


class AssertVersionMetadataMatchesDBTestCase(BaseTestCase):
    """Tests for assert_version_metadata_matches_db."""

    def test_matching_spk_does_not_raise(self):
        # An SPK whose metadata exactly matches the DB version must pass silently.
        build = BuildFactory()
        db.session.commit()
        with create_spk(build) as f:
            spk = SPK(f)
        # Should not raise
        assert_version_metadata_matches_db(build.version, spk)

    def test_mismatched_displayname_raises(self):
        build = BuildFactory()
        db.session.commit()
        existing = build.version.displaynames["enu"].displayname
        info = create_info(build)
        info["displayname"] = existing + " MODIFIED"
        info["displayname_enu"] = existing + " MODIFIED"
        with create_spk(build, info=info) as f:
            spk = SPK(f)
        with self.assertRaises(ValueError) as cm:
            assert_version_metadata_matches_db(build.version, spk)
        self.assertIn("displaynames", str(cm.exception))

    def test_mismatched_upstream_version_raises(self):
        build = BuildFactory(version__upstream_version="1.0.0")
        db.session.commit()
        info = create_info(build)
        info["version"] = f"2.0.0-{build.version.version}"
        with create_spk(build, info=info) as f:
            spk = SPK(f)
        with self.assertRaises(ValueError) as cm:
            assert_version_metadata_matches_db(build.version, spk)
        self.assertIn("upstream_version", str(cm.exception))

    def test_mismatched_service_dependencies_raises(self):
        build = BuildFactory(version__service_dependencies=[])
        db.session.commit()
        info = create_info(build)
        info["install_dep_services"] = "apache-web"
        with create_spk(build, info=info) as f:
            spk = SPK(f)
        with self.assertRaises(ValueError) as cm:
            assert_version_metadata_matches_db(build.version, spk)
        self.assertIn("service_dependencies", str(cm.exception))

    def test_error_message_lists_all_mismatches(self):
        # Multiple mismatching fields should all appear in the error message.
        build = BuildFactory()
        db.session.commit()
        existing_displayname = build.version.displaynames["enu"].displayname
        info = create_info(build)
        info["displayname"] = existing_displayname + " MODIFIED"
        info["displayname_enu"] = existing_displayname + " MODIFIED"
        info["version"] = f"9.9.9-{build.version.version}"
        with create_spk(build, info=info) as f:
            spk = SPK(f)
        with self.assertRaises(ValueError) as cm:
            assert_version_metadata_matches_db(build.version, spk)
        error = str(cm.exception)
        self.assertIn("displaynames", error)
        self.assertIn("upstream_version", error)


class PopulateDBTestCase(BaseTestCase):
    def test_dependency_packages_exist(self):
        git_package = PackageFactory(name="git")
        sickbeard_package = PackageFactory(name="sickbeard")

        BuildFactory(
            version__package=sickbeard_package,
            buildmanifest={"dependencies": git_package.name},
        )

        db.session.commit()

        sickbeard = Package.find("sickbeard")
        self.assertIsNotNone(sickbeard)

        dependency_names = {
            dependency
            for version in sickbeard.versions
            for build in version.builds
            if build.buildmanifest and build.buildmanifest.dependencies
            for dependency in build.buildmanifest.dependencies.split(":")
            if dependency
        }

        self.assertEqual({git_package.name}, dependency_names)

        for dependency in dependency_names:
            self.assertIsNotNone(
                Package.find(dependency),
                f"Expected dependency package '{dependency}' to exist",
            )
