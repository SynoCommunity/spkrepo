# -*- coding: utf-8 -*-
import base64
import json
import os
import warnings
from datetime import datetime, timedelta, timezone

from flask import current_app, url_for
from sqlalchemy.exc import SAWarning

from spkrepo.ext import db
from spkrepo.models import Architecture, Build, Firmware, Role
from spkrepo.tests.common import (
    BaseTestCase,
    BuildFactory,
    IconFactory,
    PackageFactory,
    UserFactory,
    create_info,
    create_spk,
)


def authorization_header(user):
    auth_str = user.api_key + ":"
    encoded_auth = base64.b64encode(auth_str.encode("utf-8")).decode("ascii")
    return {"Authorization": "Basic " + encoded_auth}


class PackagesTestCase(BaseTestCase):
    def assertBuildInserted(self, inserted_build, build, publisher):
        # build
        self.assertEqual(inserted_build.architectures, build.architectures)
        self.assertIs(inserted_build.firmware_min, build.firmware_min)
        self.assertIs(inserted_build.firmware_max, build.firmware_max)
        self.assertIs(inserted_build.publisher, publisher)
        self.assertIsNotNone(inserted_build.size)
        self.assertGreater(inserted_build.size, 0)
        self.assertAlmostEqual(
            inserted_build.insert_date,
            datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None),
            delta=timedelta(seconds=10),
        )
        self.assertFalse(inserted_build.active)

        # version
        self.assertEqual(inserted_build.version.version, build.version.version)
        self.assertEqual(
            inserted_build.version.upstream_version, build.version.upstream_version
        )
        self.assertEqual(inserted_build.version.changelog, build.version.changelog)
        self.assertEqual(inserted_build.version.report_url, build.version.report_url)
        self.assertEqual(inserted_build.version.distributor, build.version.distributor)
        self.assertEqual(
            inserted_build.version.distributor_url, build.version.distributor_url
        )
        self.assertEqual(inserted_build.version.maintainer, build.version.maintainer)
        self.assertEqual(
            inserted_build.version.maintainer_url, build.version.maintainer_url
        )
        self.assertEqual(
            inserted_build.version.service_dependencies,
            build.version.service_dependencies,
        )
        self.assertDictEqual(
            {
                language: displayname.displayname
                for language, displayname in inserted_build.version.displaynames.items()
            },
            {
                language: displayname.displayname
                for language, displayname in build.version.displaynames.items()
            },
        )
        self.assertDictEqual(
            {
                language: description.description
                for language, description in inserted_build.version.descriptions.items()
            },
            {
                language: description.description
                for language, description in build.version.descriptions.items()
            },
        )
        self.assertEqual(
            set(inserted_build.version.icons.keys()), set(build.version.icons.keys())
        )
        self.assertEqual(
            inserted_build.version.install_wizard, build.version.install_wizard
        )
        self.assertEqual(
            inserted_build.version.upgrade_wizard, build.version.upgrade_wizard
        )
        # api.py defaults version_startable=True when INFO omits the startable key,
        # so a factory build with startable=None should be inserted as startable=True.
        expected_startable = (
            True if build.version.startable is None else build.version.startable
        )
        self.assertEqual(inserted_build.version.startable, expected_startable)
        self.assertEqual(inserted_build.version.license, build.version.license)

        # manifest
        self.assertIsNotNone(inserted_build.buildmanifest)
        self.assertEqual(
            inserted_build.buildmanifest.dependencies,
            build.buildmanifest.dependencies,
        )
        self.assertEqual(
            inserted_build.buildmanifest.conflicts,
            build.buildmanifest.conflicts,
        )
        self.assertEqual(
            inserted_build.buildmanifest.conf_dependencies,
            build.buildmanifest.conf_dependencies,
        )
        self.assertEqual(
            inserted_build.buildmanifest.conf_conflicts,
            build.buildmanifest.conf_conflicts,
        )
        self.assertEqual(
            inserted_build.buildmanifest.conf_privilege,
            build.buildmanifest.conf_privilege,
        )
        self.assertEqual(
            inserted_build.buildmanifest.conf_resource,
            build.buildmanifest.conf_resource,
        )

        # package
        self.assertEqual(
            inserted_build.version.package.name, build.version.package.name
        )

        # filesystem
        for icon in inserted_build.version.icons.values():
            self.assertTrue(
                os.path.exists(os.path.join(current_app.config["DATA_PATH"], icon.path))
            )
        self.assertTrue(
            os.path.exists(
                os.path.join(current_app.config["DATA_PATH"], inserted_build.path)
            )
        )

    def test_post_anonymous_user(self):
        self.assert401(self.client.post(url_for("api.packages")))

    def test_post_simple_user(self):
        # A user with a valid api_key but no developer role must be rejected.
        user = UserFactory(roles=[])
        db.session.commit()

        self.assert401(
            self.client.post(
                url_for("api.packages"), headers=authorization_header(user)
            )
        )

    def test_post_no_data(self):
        user = UserFactory(roles=[Role.find("developer")])
        db.session.commit()

        response = self.client.post(
            url_for("api.packages"), headers=authorization_header(user)
        )
        self.assert400(response)
        self.assertIn("No data to process", response.data.decode())

    def test_post_minimum(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build()
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_conflict(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        architectures = [Architecture.find("88f628x"), Architecture.find("cedarview")]
        build = BuildFactory.build(architectures=architectures)
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
            spk.seek(0)
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert409(response)
        self.assertIn(
            "Conflicting architectures: 88f628x, cedarview",
            response.data.decode(),
        )

    def test_post_allows_different_firmware_same_architecture(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        # Pin to the lowest seeded firmware so newer_firmware is always strictly higher.
        base_build = BuildFactory.build(
            architectures=[Architecture.find("noarch")],
            firmware_min=Firmware.query.order_by(Firmware.build.asc()).first(),
        )
        with (
            create_spk(base_build) as spk,
            warnings.catch_warnings(record=True) as base_warns,
        ):
            warnings.simplefilter("always", SAWarning)
            first_response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert201(first_response)
        base_sa_warnings = [w for w in base_warns if issubclass(w.category, SAWarning)]
        self.assertFalse(
            base_sa_warnings,
            (
                "Unexpected SAWarnings encountered: "
                f"{[str(w.message) for w in base_sa_warnings]}"
            ),
        )

        # Always use the highest seeded firmware to guarantee it is genuinely newer
        # than whatever the factory picked for base_build, avoiding a flaky fixture.
        newer_firmware = Firmware.query.order_by(Firmware.build.desc()).first()
        self.assertIsNotNone(newer_firmware)
        self.assertGreater(
            newer_firmware.build,
            base_build.firmware_min.build,
            "Expected newer_firmware to be strictly higher than base firmware",
        )

        followup_build = BuildFactory.build(
            version=base_build.version,
            architectures=base_build.architectures,
            firmware_min=newer_firmware,
        )
        with (
            create_spk(followup_build) as spk,
            warnings.catch_warnings(record=True) as caught,
        ):
            warnings.simplefilter("always", SAWarning)
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )

        self.assert201(response)
        sa_warnings = [w for w in caught if issubclass(w.category, SAWarning)]
        self.assertFalse(
            sa_warnings,
            (
                "Unexpected SAWarnings encountered: "
                f"{[str(w.message) for w in sa_warnings]}"
            ),
        )

    def test_post_new_package_not_author_not_maintainer_user(self):
        user = UserFactory(roles=[Role.find("developer")])
        db.session.commit()

        with create_spk(BuildFactory.build()) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert403(response)
        self.assertIn(
            "Insufficient permissions to create new packages",
            response.data.decode(),
        )

    def test_post_existing_package_not_author_not_maintainer_user(self):
        user = UserFactory(roles=[Role.find("developer")])
        package = PackageFactory()
        db.session.commit()

        with create_spk(BuildFactory.build(version__package=package)) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert403(response)
        self.assertIn(
            "Insufficient permissions on this package",
            response.data.decode(),
        )

    def test_post_existing_package_maintainer_user(self):
        user = UserFactory(roles=[Role.find("developer")])
        package = PackageFactory(maintainers=[user])
        db.session.commit()

        build = BuildFactory.build(version__package=package)
        db.session.expire(package)
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )

    def test_post_unknown_architecture(self):
        user = UserFactory(roles=[Role.find("developer")])
        db.session.commit()

        build = BuildFactory.build(architectures=[Architecture(code="newarch")])
        with create_spk(build) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Unknown architecture: newarch", response.data.decode())

    def test_post_invalid_firmware(self):
        user = UserFactory(roles=[Role.find("developer")])
        db.session.commit()

        build = BuildFactory.build(firmware_min=Firmware(version="1.0", build=42))
        with create_spk(build) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Invalid firmware", response.data.decode())

    def test_post_unknown_firmware(self):
        user = UserFactory(roles=[Role.find("developer")])
        db.session.commit()

        build = BuildFactory.build(firmware_min=Firmware(version="1.0", build=421))
        with create_spk(build) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Unknown firmware", response.data.decode())

    def test_post_icons_in_info_only(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build()
        with create_spk(build, with_package_icons=False, with_info_icons=True) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_icons_in_both(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build()
        with create_spk(build, with_package_icons=True, with_info_icons=True) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_no_license(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(version__license=None)
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_install_wizard(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(version__install_wizard=True)
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_upgrade_wizard(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(version__upgrade_wizard=True)
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_120_icon(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(
            version__icons={"120": IconFactory.build(size="120")}
        )
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_startable(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(version__startable=True)
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_not_startable(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(version__startable=False)
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_wrong_displayname_language(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build()
        info = create_info(build)
        info["displayname_zzz"] = "displayname_zzz"
        with create_spk(build, info=info) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Unknown INFO displayname language", response.data.decode())

    def test_post_wrong_description_language(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build()
        info = create_info(build)
        info["description_zzz"] = "description_zzz"
        with create_spk(build, info=info) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Unknown INFO description language", response.data.decode())

    def test_post_wrong_version(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build()
        info = create_info(build)
        info["version"] = "1.2.3~4"
        with create_spk(build, info=info) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Invalid version", response.data.decode())

    def test_post_signed(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build()
        with create_spk(build, signature="signature") as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Package contains a signature", response.data.decode())

    def test_post_invalid_spk(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build()
        with create_spk(build) as spk:
            spk.seek(100)
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Invalid SPK", response.data.decode())

    def test_post_existing_version_matching_upstream(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(
            version__upstream_version="1.0.0",
            architectures=[Architecture.find("88f6281", syno=True)],
        )
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )

        new_build = BuildFactory.build(
            version=build.version,
            architectures=[Architecture.find("cedarview", syno=True)],
        )
        with create_spk(new_build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )

    def test_post_existing_version_mismatched_upstream(self):
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(
            version__upstream_version="1.0.0",
            architectures=[Architecture.find("88f6281", syno=True)],
        )
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )

        new_build = BuildFactory.build(
            version__upstream_version="2.0.0",
            version__version=build.version.version,
            version__package=build.version.package,
            architectures=[Architecture.find("cedarview", syno=True)],
        )
        with create_spk(new_build) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Upstream version mismatch", response.data.decode())

    def test_post_201_response_body(self):
        # The 201 response body must contain package, version, firmware, architectures.
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(
            architectures=[Architecture.find("88f628x")],
            firmware_min=Firmware.find(1594),
        )
        with create_spk(build) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert201(response)
        body = json.loads(response.data.decode())
        self.assertEqual(body["package"], build.version.package.name)
        self.assertEqual(body["version"], build.version.version_string)
        self.assertEqual(body["firmware"], build.firmware_min.firmware_string)
        self.assertEqual(body["architectures"], ["88f628x"])

    def test_post_with_firmware_max(self):
        # A build with firmware_max set should be accepted and stored correctly.
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(
            firmware_min=Firmware.find(1594),
            firmware_max=Firmware.find(4458),
        )
        with create_spk(build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )
        self.assertBuildInserted(Build.query.one(), build, user)

    def test_post_invalid_firmware_max(self):
        # os_max_ver that doesn't match the firmware regex returns 422.
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(firmware_min=Firmware.find(1594))
        info = create_info(build)
        info["os_max_ver"] = "not-a-firmware"
        with create_spk(build, info=info) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Invalid maximum firmware", response.data.decode())

    def test_post_unknown_firmware_max(self):
        # os_max_ver with valid format but unknown build number returns 422.
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(firmware_min=Firmware.find(1594))
        info = create_info(build)
        info["os_max_ver"] = "5.0-9999"
        with create_spk(build, info=info) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Unknown maximum firmware", response.data.decode())

    def test_post_firmware_max_less_than_firmware_min(self):
        # os_max_ver < firmware returns 422.
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        # firmware_min=4458, firmware_max=1594 (max < min)
        build = BuildFactory.build(firmware_min=Firmware.find(4458))
        info = create_info(build)
        info["os_max_ver"] = Firmware.find(1594).firmware_string
        with create_spk(build, info=info) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn(
            "Maximum firmware must be greater than or equal to minimum firmware",
            response.data.decode(),
        )

    def test_post_conflict_firmware_max_range_overlap(self):
        # Two builds with overlapping firmware ranges on the same arch should conflict.
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        arch = [Architecture.find("88f628x")]
        first_build = BuildFactory.build(
            architectures=arch,
            firmware_min=Firmware.find(1594),
            firmware_max=Firmware.find(4458),
        )
        with create_spk(first_build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )

        # Second build: same arch, firmware range overlaps (min=4458, no max)
        second_build = BuildFactory.build(
            version=first_build.version,
            architectures=arch,
            firmware_min=Firmware.find(4458),
            firmware_max=None,
        )
        with create_spk(second_build) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert409(response)
        self.assertIn("Conflicting architectures", response.data.decode())

    def test_post_no_conflict_non_overlapping_firmware_ranges(self):
        # Two builds on the same arch with non-overlapping firmware ranges are allowed.
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        arch = [Architecture.find("88f628x")]
        first_build = BuildFactory.build(
            architectures=arch,
            firmware_min=Firmware.find(1594),
            firmware_max=Firmware.find(1594),
        )
        with create_spk(first_build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )

        second_build = BuildFactory.build(
            version=first_build.version,
            architectures=arch,
            firmware_min=Firmware.find(4458),
            firmware_max=None,
        )
        with create_spk(second_build) as spk:
            self.assert201(
                self.client.post(
                    url_for("api.packages"),
                    headers=authorization_header(user),
                    data=spk.read(),
                )
            )

    def test_post_unknown_install_dep_service(self):
        # An unknown install_dep_services value returns 422.
        user = UserFactory(roles=[Role.find("developer"), Role.find("package_admin")])
        db.session.commit()

        build = BuildFactory.build(version__service_dependencies=[])
        info = create_info(build)
        info["install_dep_services"] = "no-such-service"
        with create_spk(build, info=info) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn(
            "Unknown dependent service: no-such-service", response.data.decode()
        )

    def test_post_maintainer_cannot_upload_to_other_package(self):
        # A maintainer on package A must be rejected when uploading to package B.
        user = UserFactory(roles=[Role.find("developer")])
        PackageFactory(
            maintainers=[user]
        )  # establishes user as maintainer on a different package
        package_b = PackageFactory()
        db.session.commit()

        with create_spk(BuildFactory.build(version__package=package_b)) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert403(response)
        self.assertIn(
            "Insufficient permissions on this package", response.data.decode()
        )
