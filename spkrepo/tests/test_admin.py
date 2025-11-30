# -*- coding: utf-8 -*-
import os

from flask import current_app, url_for

from spkrepo.ext import db
from spkrepo.models import Build, Firmware, Package, Version
from spkrepo.tests.common import (
    BaseTestCase,
    BuildFactory,
    PackageFactory,
    VersionFactory,
    create_image,
)


class IndexTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert302(self.client.get(url_for("admin.index"), follow_redirects=False))

    def test_anonymous_redirects_to_login(self):
        self.assertRedirectsTo(
            self.client.get(url_for("admin.index")),
            url_for("security.login"),
        )

    def test_user(self):
        with self.logged_user():
            self.assert403(self.client.get(url_for("admin.index")))

    def test_developer(self):
        with self.logged_user("developer"):
            self.assert200(self.client.get(url_for("admin.index")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("admin.index")))

    def test_admin(self):
        with self.logged_user("admin"):
            self.assert200(self.client.get(url_for("admin.index")))


class UserTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert403(self.client.get(url_for("user.index_view")))

    def test_user(self):
        with self.logged_user():
            self.assert403(self.client.get(url_for("user.index_view")))

    def test_developer(self):
        with self.logged_user("developer"):
            self.assert403(self.client.get(url_for("user.index_view")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert403(self.client.get(url_for("user.index_view")))

    def test_admin(self):
        with self.logged_user("admin"):
            self.assert200(self.client.get(url_for("user.index_view")))

    def test_action_activate_one(self):
        with self.logged_user("admin"):
            user = self.create_user()
            user.active = False
            db.session.commit()
            response = self.client.post(
                url_for("user.action_view"),
                follow_redirects=True,
                data=dict(action="activate", rowid=[user.id]),
            )
            self.assert200(response)
            self.assertIn(
                "User was successfully activated.",
                response.data.decode(),
            )
            self.assertTrue(user.active)

    def test_action_activate_multi(self):
        with self.logged_user("admin"):
            user1 = self.create_user()
            user1.active = False
            user2 = self.create_user()
            user2.active = False
            db.session.commit()
            response = self.client.post(
                url_for("user.action_view"),
                follow_redirects=True,
                data=dict(action="activate", rowid=[user1.id, user2.id]),
            )
            self.assert200(response)
            self.assertIn(
                "2 users were successfully activated.",
                response.data.decode(),
            )
            self.assertTrue(user1.active)
            self.assertTrue(user2.active)

    def test_action_deactivate(self):
        with self.logged_user("admin"):
            user = self.create_user()
            user.active = True
            db.session.commit()
            response = self.client.post(
                url_for("user.action_view"),
                follow_redirects=True,
                data=dict(action="deactivate", rowid=[user.id]),
            )
            self.assert200(response)
            self.assertIn(
                "User was successfully deactivated.",
                response.data.decode(),
            )
            self.assertFalse(user.active)

    def test_action_deactivate_multi(self):
        with self.logged_user("admin"):
            user1 = self.create_user()
            user1.active = True
            user2 = self.create_user()
            user2.active = True
            db.session.commit()
            response = self.client.post(
                url_for("user.action_view"),
                follow_redirects=True,
                data=dict(action="deactivate", rowid=[user1.id, user2.id]),
            )
            self.assert200(response)
            self.assertIn(
                "2 users were successfully deactivated.",
                response.data.decode(),
            )
            self.assertFalse(user1.active)
            self.assertFalse(user2.active)


class PackageTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert403(self.client.get(url_for("package.index_view")))

    def test_user(self):
        with self.logged_user():
            self.assert403(self.client.get(url_for("package.index_view")))

    def test_developer(self):
        with self.logged_user("developer"):
            self.assert403(self.client.get(url_for("package.index_view")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("package.index_view")))

    def test_admin(self):
        with self.logged_user("admin"):
            self.assert403(self.client.get(url_for("package.index_view")))

    def test_on_model_create(self):
        self.assertEqual(len(Package.query.all()), 0)
        with self.logged_user("package_admin"):
            self.client.post(url_for("package.create_view"), data=dict(name="test"))
        self.assertEqual(len(Package.query.all()), 1)
        package = Package.query.one()
        package_path = os.path.join(current_app.config["DATA_PATH"], package.name)
        self.assertTrue(os.path.exists(package_path))

    def test_on_model_delete(self):
        package = PackageFactory()
        db.session.commit()
        self.assertEqual(len(Package.query.all()), 1)
        package_path = os.path.join(current_app.config["DATA_PATH"], package.name)
        self.assertTrue(os.path.exists(package_path))
        with self.logged_user("package_admin", "admin"):
            self.client.post(url_for("package.delete_view", id=str(package.id)))
        self.assertEqual(len(Package.query.all()), 0)
        self.assertTrue(not os.path.exists(package_path))


class VersionTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert403(self.client.get(url_for("version.index_view")))

    def test_user(self):
        with self.logged_user():
            self.assert403(self.client.get(url_for("version.index_view")))

    def test_developer(self):
        with self.logged_user("developer"):
            self.assert200(self.client.get(url_for("version.index_view")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("version.index_view")))

    def test_admin(self):
        with self.logged_user("admin"):
            self.assert403(self.client.get(url_for("version.index_view")))

    def test_on_model_delete(self):
        version = VersionFactory()
        db.session.commit()
        self.assertEqual(len(Version.query.all()), 1)
        version_path = os.path.join(
            current_app.config["DATA_PATH"], version.package.name, str(version.version)
        )
        self.assertTrue(os.path.exists(version_path))
        with self.logged_user("package_admin", "admin"):
            self.client.post(url_for("version.delete_view", id=str(version.id)))
        self.assertEqual(len(Version.query.all()), 0)
        self.assertTrue(not os.path.exists(version_path))

    def test_action_resync_requires_admin(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("version.index_view"))
            self.assert200(response)
            self.assertNotIn("Resync INFO", response.data.decode())

    def test_action_resync_refreshes_metadata(self):
        build = BuildFactory()
        db.session.commit()

        version = build.version
        original_display = version.displaynames["enu"].displayname
        original_description = version.descriptions["enu"].description
        original_services = sorted(
            service.code for service in version.service_dependencies
        )
        original_upstream = version.upstream_version
        original_license = version.license
        original_architectures = sorted(arch.code for arch in build.architectures)
        original_firmware_min = build.firmware_min
        original_firmware_max = build.firmware_max
        original_dependencies = build.buildmanifest.dependencies
        original_conf_privilege = build.buildmanifest.conf_privilege

        version.displaynames["enu"].displayname = "Changed"
        version.descriptions["enu"].description = "Changed"
        version.service_dependencies = []
        version.upstream_version = "0.0.0"
        version.license = None

        for key in list(version.icons.keys()):
            del version.icons[key]

        alternative_firmware = Firmware.query.filter(
            Firmware.id != original_firmware_min.id
        ).first()
        if alternative_firmware is not None:
            build.firmware_min = alternative_firmware
        build.firmware_max = None
        build.architectures = []
        build.buildmanifest.dependencies = None
        build.buildmanifest.conf_privilege = None
        build.checksum = None
        build.md5 = None

        db.session.commit()

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[version.id]),
            )
            self.assert200(response)
            self.assertIn("metadata refreshed from INFO", response.data.decode())

        db.session.expire_all()
        refreshed_build = db.session.get(Build, build.id)
        refreshed_version = refreshed_build.version

        self.assertEqual(
            refreshed_version.displaynames["enu"].displayname, original_display
        )
        self.assertEqual(
            refreshed_version.descriptions["enu"].description, original_description
        )
        self.assertEqual(
            sorted(service.code for service in refreshed_version.service_dependencies),
            original_services,
        )
        self.assertEqual(refreshed_version.upstream_version, original_upstream)
        self.assertEqual(refreshed_version.license, original_license)
        self.assertTrue({"72", "256"}.intersection(refreshed_version.icons.keys()))
        self.assertEqual(
            sorted(arch.code for arch in refreshed_build.architectures),
            original_architectures,
        )
        self.assertEqual(refreshed_build.firmware_min.id, original_firmware_min.id)
        if original_firmware_max is None:
            self.assertIsNone(refreshed_build.firmware_max)
        else:
            self.assertEqual(
                refreshed_build.firmware_max.id,
                original_firmware_max.id,
            )
        self.assertEqual(
            refreshed_build.buildmanifest.dependencies,
            original_dependencies,
        )
        self.assertEqual(
            refreshed_build.buildmanifest.conf_privilege,
            original_conf_privilege,
        )
        self.assertEqual(refreshed_build.md5, refreshed_build.calculate_md5())


class BuildTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert403(self.client.get(url_for("build.index_view")))

    def test_user(self):
        with self.logged_user():
            self.assert403(self.client.get(url_for("build.index_view")))

    def test_developer(self):
        with self.logged_user("developer"):
            self.assert200(self.client.get(url_for("build.index_view")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("build.index_view")))

    def test_admin(self):
        with self.logged_user("admin"):
            self.assert403(self.client.get(url_for("build.index_view")))

    def test_action_activate_one(self):
        with self.logged_user("package_admin"):
            build = BuildFactory(active=False)
            db.session.commit()
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="activate", rowid=[build.id]),
            )
            self.assert200(response)
            self.assertIn(
                "Build was successfully activated.",
                response.data.decode(),
            )
            self.assertTrue(build.active)

    def test_action_activate_multi(self):
        with self.logged_user("package_admin"):
            build1 = BuildFactory(active=False)
            build2 = BuildFactory(active=False)
            db.session.commit()
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="activate", rowid=[build1.id, build2.id]),
            )
            self.assert200(response)
            self.assertIn(
                "2 builds were successfully activated.",
                response.data.decode(),
            )
            self.assertTrue(build1.active)
            self.assertTrue(build2.active)

    def test_action_deactivate(self):
        with self.logged_user("package_admin"):
            build = BuildFactory(active=True)
            db.session.commit()
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="deactivate", rowid=[build.id]),
            )
            self.assert200(response)
            self.assertIn(
                "Build was successfully deactivated.",
                response.data.decode(),
            )
            self.assertFalse(build.active)

    def test_action_deactivate_multi(self):
        with self.logged_user("package_admin"):
            build1 = BuildFactory(active=True)
            build2 = BuildFactory(active=True)
            db.session.commit()
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="deactivate", rowid=[build1.id, build2.id]),
            )
            self.assert200(response)
            self.assertIn(
                "2 builds were successfully deactivated.",
                response.data.decode(),
            )
            self.assertFalse(build1.active)
            self.assertFalse(build2.active)

    def test_action_resync_requires_admin(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("build.index_view"))
            self.assert200(response)
            self.assertNotIn("Resync INFO", response.data.decode())

    def test_action_resync_refreshes_single_build(self):
        build = BuildFactory()
        db.session.commit()

        original_display = build.version.displaynames["enu"].displayname
        original_architectures = sorted(arch.code for arch in build.architectures)

        build.version.displaynames["enu"].displayname = "Altered"
        build.architectures = []
        db.session.commit()

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.id]),
            )
            self.assert200(response)
            self.assertIn("metadata refreshed from INFO", response.data.decode())

        db.session.expire_all()
        refreshed_build = db.session.get(Build, build.id)

        self.assertEqual(
            refreshed_build.version.displaynames["enu"].displayname,
            original_display,
        )
        self.assertEqual(
            sorted(arch.code for arch in refreshed_build.architectures),
            original_architectures,
        )


class ScreenshotTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert403(self.client.get(url_for("screenshot.index_view")))

    def test_user(self):
        with self.logged_user():
            self.assert403(self.client.get(url_for("screenshot.index_view")))

    def test_developer(self):
        with self.logged_user("developer"):
            self.assert403(self.client.get(url_for("screenshot.index_view")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("screenshot.index_view")))

    def test_admin(self):
        with self.logged_user("admin"):
            self.assert403(self.client.get(url_for("screenshot.index_view")))

    def test_create(self):
        package = PackageFactory(add_screenshot=False)
        db.session.commit()
        self.assertEqual(len(package.screenshots), 0)
        with self.logged_user("package_admin"):
            self.client.post(
                url_for("screenshot.create_view"),
                data=dict(
                    package=str(package.id),
                    path=(create_image("Test", 1280, 1024), "test.png"),
                ),
            )
        self.assertEqual(len(package.screenshots), 1)
        self.assertTrue(package.screenshots[0].path.endswith("screenshot_1.png"))
