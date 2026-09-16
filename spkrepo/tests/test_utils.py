# -*- coding: utf-8 -*-
import io
import json
import tarfile

from mock import Mock

from spkrepo.adapters.spk_io import SPK
from spkrepo.domain.versions import (
    assert_version_metadata_matches_db,
    extract_version_metadata,
)
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

    def test_info_text_variants(self):
        # Single tar-wiring probe for INFO text tolerance + booleans.
        # Branch tables live in domain units (parse_info_lines).
        build = BuildFactory.build()
        info = io.BytesIO(
            "\n".join([f'{k}="{v}"\n' for k, v in create_info(build).items()]).encode(
                "utf-8"
            )
        )
        with create_spk(build, info=info) as f:
            SPK(f)
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

    def test_wrong_file_encodings(self):
        cases = [
            (
                "LICENSE",
                dict(version__license="License française"),
                dict(license_encoding="latin-1"),
                "Wrong LICENSE encoding",
                None,
            ),
            (
                "syno_signature",
                {},
                dict(signature="Signature française", signature_encoding="latin-1"),
                "Wrong syno_signature.asc encoding",
                None,
            ),
            (
                "INFO",
                {},
                dict(info_encoding="latin-1"),
                "Wrong INFO encoding",
                {"description": "Description en français"},
            ),
            (
                "PKG_DEPS",
                dict(
                    buildmanifest__conf_dependencies=json.dumps(
                        {"déçu": {"dsm_min_ver": "5.0-4300"}}
                    )
                ),
                dict(conf_dependencies_encoding="latin-1"),
                "Wrong conf/PKG_DEPS encoding",
                None,
            ),
            (
                "PKG_CONX",
                dict(
                    buildmanifest__conf_conflicts=json.dumps(
                        {"déçu": {"dsm_min_ver": "5.0-4300"}}
                    )
                ),
                dict(conf_conflicts_encoding="latin-1"),
                "Wrong conf/PKG_CONX encoding",
                None,
            ),
            (
                "privilege",
                dict(
                    buildmanifest__conf_privilege=json.dumps(
                        {"déçu": {"run-as": "<run-as>"}}, ensure_ascii=False
                    )
                ),
                dict(conf_privilege_encoding="latin-1"),
                "Wrong conf/privilege encoding",
                None,
            ),
            (
                "resource",
                dict(
                    buildmanifest__conf_resource=json.dumps(
                        {"déçu": {"<resource-id>": "<specification>"}},
                        ensure_ascii=False,
                    )
                ),
                dict(conf_resource_encoding="latin-1"),
                "Wrong conf/resource encoding",
                None,
            ),
        ]
        for name, factory_kwargs, spk_kwargs, expected, info_override in cases:
            with self.subTest(encoding=name):
                build = BuildFactory.build(**factory_kwargs)
                info = None
                if info_override is not None:
                    info = create_info(build)
                    info.update(info_override)
                    spk_kwargs = dict(spk_kwargs, info=info)
                with create_spk(build, **spk_kwargs) as f:
                    with self.assertRaises(SPKParseError) as cm:
                        SPK(f)
                self.assertEqual(expected, str(cm.exception))

    def test_invalid_info_wiring(self):
        """Single tar->domain wiring probe for INFO rejection messages.

        Parse branches live in domain units (parse_info_lines); this keeps
        one probe per message proving the adapter propagates the error.
        """
        build = BuildFactory.build()
        base_info = create_info(build)
        cases = [
            (
                io.BytesIO(
                    "\n".join([f"{k}={v}" for k, v in base_info.items()]).encode(
                        "utf-8"
                    )
                ),
                "Invalid INFO",
            ),
            (
                dict(base_info, package_icon_120="package_icon_120"),
                "Invalid INFO icon: package_icon_120",
            ),
            (dict(base_info, startable="Something"), "Invalid INFO boolean: startable"),
            (None, "Invalid INFO package"),  # special-cased below
            ("__del_package__", "Missing INFO: package"),
        ]
        for info_arg, expected in cases:
            with self.subTest(expected=expected):
                if info_arg is None:
                    bad = BuildFactory.build(
                        version__package__name="Invalid package name"
                    )
                    ctx = create_spk(bad)
                elif info_arg == "__del_package__":
                    info = dict(base_info)
                    del info["package"]
                    ctx = create_spk(build, info=info)
                elif isinstance(info_arg, io.BytesIO):
                    ctx = create_spk(build, info=info_arg)
                else:
                    ctx = create_spk(build, info=info_arg)
                with ctx as f:
                    with self.assertRaises(SPKParseError) as cm:
                        SPK(f)
                self.assertEqual(expected, str(cm.exception))

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

    def test_conf_folder_missing_or_empty(self):
        for with_conf, expected in (
            (False, "Missing conf folder"),
            (True, "Empty conf folder"),
        ):
            with self.subTest(with_conf=with_conf):
                build = BuildFactory.build(
                    buildmanifest__conf_dependencies=None,
                    buildmanifest__conf_conflicts=None,
                    buildmanifest__conf_privilege=None,
                    buildmanifest__conf_resource=None,
                )
                info = create_info(build)
                info["support_conf_folder"] = "yes"
                with create_spk(build, info=info, with_conf=with_conf) as f:
                    with self.assertRaises(SPKParseError) as cm:
                        SPK(f)
                self.assertEqual(expected, str(cm.exception))

    def test_conf_invalid_json(self):
        for field, expected in (
            ("buildmanifest__conf_privilege", "File conf/privilege is not valid JSON"),
            ("buildmanifest__conf_resource", "File conf/resource is not valid JSON"),
        ):
            with self.subTest(field=field):
                build = BuildFactory.build(**{field: '{"invalid": "json}'})
                with create_spk(build) as f:
                    with self.assertRaises(SPKParseError) as cm:
                        SPK(f)
                self.assertEqual(expected, str(cm.exception))


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
    """Single tar-wiring probe for extract_version_metadata.

    Branch table below is fake-based (no DB/tar); truth Retired from
    test_domain to keep that suite boundary-free.
    """

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


class AssertVersionMetadataMatchesDBTestCase(BaseTestCase):
    """Single tar→DB wiring probe for the consistency check.

    Mismatch truth table lives in domain units (fakes, no DB/tar).
    """

    def test_matching_spk_does_not_raise(self):
        # An SPK whose metadata exactly matches the DB version must pass silently.
        build = BuildFactory()
        db.session.commit()
        with create_spk(build) as f:
            spk = SPK(f)
        # Should not raise
        assert_version_metadata_matches_db(build.version, spk)


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
