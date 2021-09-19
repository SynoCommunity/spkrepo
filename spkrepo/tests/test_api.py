# -*- coding: utf-8 -*-
import base64
import datetime
import os
from unittest import TestLoader, TestSuite

from flask import current_app, url_for

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
    return {
        "Authorization": b"Basic "
        + base64.b64encode(user.api_key.encode("utf-8") + b":")
    }


class PackagesTestCase(BaseTestCase):
    def assertBuildInserted(self, inserted_build, build, publisher):
        # build
        self.assertEqual(inserted_build.architectures, build.architectures)
        self.assertIs(inserted_build.firmware, build.firmware)
        self.assertIs(inserted_build.publisher, publisher)
        self.assertEqual(inserted_build.extract_size, build.extract_size)
        self.assertAlmostEqual(
            inserted_build.insert_date,
            datetime.datetime.utcnow().replace(microsecond=0),
            delta=datetime.timedelta(seconds=10),
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
            inserted_build.version.dependencies, build.version.dependencies
        )
        self.assertEqual(inserted_build.version.conflicts, build.version.conflicts)
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
        self.assertEqual(inserted_build.version.startable, build.version.startable)
        self.assertEqual(inserted_build.version.license, build.version.license)

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
        user = UserFactory()
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
        self.assertIn("No data to process", response.data.decode(response.charset))

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
            response.data.decode(response.charset),
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
            response.data.decode(response.charset),
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
            response.data.decode(response.charset),
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
        self.assertIn(
            "Unknown architecture: newarch", response.data.decode(response.charset)
        )

    def test_post_invalid_firmware(self):
        user = UserFactory(roles=[Role.find("developer")])
        db.session.commit()

        build = BuildFactory.build(firmware=Firmware(version="1.0", build=42))
        with create_spk(build) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Invalid firmware", response.data.decode(response.charset))

    def test_post_unknown_firmware(self):
        user = UserFactory(roles=[Role.find("developer")])
        db.session.commit()

        build = BuildFactory.build(firmware=Firmware(version="1.0", build=421))
        with create_spk(build) as spk:
            response = self.client.post(
                url_for("api.packages"),
                headers=authorization_header(user),
                data=spk.read(),
            )
        self.assert422(response)
        self.assertIn("Unknown firmware", response.data.decode(response.charset))

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
        self.assertIn(
            "Unknown INFO displayname language", response.data.decode(response.charset)
        )

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
        self.assertIn(
            "Unknown INFO description language", response.data.decode(response.charset)
        )

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
        self.assertIn("Invalid version", response.data.decode(response.charset))

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
        self.assertIn(
            "Package contains a signature", response.data.decode(response.charset)
        )

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
        self.assertIn("Invalid SPK", response.data.decode(response.charset))


def suite():
    suite = TestSuite()
    suite.addTest(TestLoader().loadTestsFromTestCase(PackagesTestCase))
    return suite
