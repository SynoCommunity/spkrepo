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
    create_info,
    create_spk,
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

    def test_action_deactivate_one(self):
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

    def test_action_resync_info_visible_to_package_admin(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("version.index_view"))
            self.assert200(response)
            self.assertIn("Resync Info", response.data.decode())

    def test_action_resync_info_requires_admin_or_package_admin(self):
        with self.logged_user("developer"):
            response = self.client.get(url_for("version.index_view"))
            self.assert200(response)
            self.assertNotIn("Resync Info", response.data.decode())

    def test_action_resync_info_refreshes_version_metadata(self):
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

        version.displaynames["enu"].displayname = "Changed"
        version.descriptions["enu"].description = "Changed"
        version.service_dependencies = []
        version.upstream_version = "0.0.0"
        version.license = None

        for key in list(version.icons.keys()):
            del version.icons[key]

        db.session.commit()

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[version.id]),
            )
            self.assert200(response)
            self.assertIn("refreshed", response.data.decode())

        db.session.expire_all()
        refreshed_version = db.session.get(Build, build.id).version

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

    def test_action_resync_info_refreshes_build_metadata(self):
        # Pin firmware_min to the lowest seeded firmware so we can always find
        # a different one to corrupt the build with.
        build = BuildFactory(
            firmware_min=Firmware.query.order_by(Firmware.build.asc()).first(),
            firmware_max=Firmware.query.order_by(Firmware.build.desc()).first(),
        )
        db.session.commit()

        version = build.version
        original_architectures = sorted(arch.code for arch in build.architectures)
        original_firmware_min = build.firmware_min
        original_firmware_max = build.firmware_max
        original_dependencies = build.buildmanifest.dependencies
        original_conf_privilege = build.buildmanifest.conf_privilege

        # Corrupt the build
        corrupting_firmware = Firmware.query.filter(
            Firmware.id != original_firmware_min.id
        ).first()
        self.assertIsNotNone(corrupting_firmware, "Need at least 2 firmware entries")
        build.firmware_min = corrupting_firmware
        build.firmware_max = None
        build.architectures = []
        build.buildmanifest.dependencies = None
        build.buildmanifest.conf_privilege = None
        build.checksum = None
        build.md5 = None

        db.session.commit()

        self.assertNotEqual(build.firmware_min.id, original_firmware_min.id)
        self.assertIsNone(build.firmware_max)

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[version.id]),
            )
            self.assert200(response)
            self.assertIn("refreshed", response.data.decode())

        db.session.expire_all()
        refreshed_build = db.session.get(Build, build.id)

        self.assertEqual(
            sorted(arch.code for arch in refreshed_build.architectures),
            original_architectures,
        )
        self.assertEqual(refreshed_build.firmware_min.id, original_firmware_min.id)
        self.assertIsNotNone(refreshed_build.firmware_max)
        self.assertEqual(refreshed_build.firmware_max.id, original_firmware_max.id)
        self.assertEqual(
            refreshed_build.buildmanifest.dependencies,
            original_dependencies,
        )
        self.assertEqual(
            refreshed_build.buildmanifest.conf_privilege,
            original_conf_privilege,
        )
        self.assertEqual(refreshed_build.md5, refreshed_build.calculate_md5())

    def test_action_resync_info_invalidates_cache(self):
        build = BuildFactory()
        db.session.commit()
        from spkrepo.ext import cache as app_cache

        app_cache.set("packages_versions", "stale")
        with self.logged_user("package_admin", "admin"):
            self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.version.id]),
            )
        self.assertIsNone(app_cache.get("packages_versions"))

    def test_action_resync_file_invalidates_cache(self):
        build = BuildFactory()
        db.session.commit()
        from spkrepo.ext import cache as app_cache

        app_cache.set("packages_versions", "stale")
        with self.logged_user("package_admin", "admin"):
            self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_file", rowid=[build.version.id]),
            )
        self.assertIsNone(app_cache.get("packages_versions"))

    def test_action_resync_info_single_build_no_siblings_succeeds(self):
        # A version with only one build must resync cleanly with no sibling check.
        build = BuildFactory()
        db.session.commit()
        self.assertEqual(len(build.version.builds), 1)
        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.version.id]),
            )
        self.assert200(response)
        self.assertIn("refreshed", response.data.decode())

    def test_action_resync_info_rejects_inconsistent_sibling_builds(self):
        # If two builds under the same version have different version-level metadata
        # on disk, resync must fail with an error rather than silently overwriting.
        build1 = BuildFactory()
        build2 = BuildFactory(version=build1.version)
        db.session.commit()

        # Overwrite build2's SPK on disk with a displayname that differs
        # from what is in the DB (and from build1's SPK).
        existing_displayname = build1.version.displaynames["enu"].displayname
        info = create_info(build2)
        info["displayname"] = existing_displayname + " SIBLING MODIFIED"
        info["displayname_enu"] = existing_displayname + " SIBLING MODIFIED"
        spk_path = os.path.join(current_app.config["DATA_PATH"], build2.path)
        with open(spk_path, "wb") as f:
            with create_spk(build2, info=info) as spk:
                f.write(spk.read())

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build1.version.id]),
            )
        self.assert200(response)
        # The flash message must report failure, not success.
        self.assertIn("Failed", response.data.decode())
        self.assertNotIn("refreshed", response.data.decode())

    def test_action_resync_file_visible_to_package_admin(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("version.index_view"))
            self.assert200(response)
            self.assertIn("Resync File", response.data.decode())

    def test_action_resync_file_requires_admin_or_package_admin(self):
        with self.logged_user("developer"):
            response = self.client.get(url_for("version.index_view"))
            self.assert200(response)
            self.assertNotIn("Resync File", response.data.decode())

    def test_action_resync_file_refreshes_builds(self):
        build = BuildFactory()
        db.session.commit()

        version = build.version
        build.md5 = None
        build.size = None
        db.session.commit()

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_file", rowid=[version.id]),
            )
            self.assert200(response)
            self.assertIn("refreshed", response.data.decode())

        db.session.expire_all()
        refreshed_build = db.session.get(Build, build.id)
        self.assertEqual(refreshed_build.md5, refreshed_build.calculate_md5())
        self.assertIsNotNone(refreshed_build.size)
        self.assertGreater(refreshed_build.size, 0)

    def test_action_activate_one(self):
        build = BuildFactory(active=False)
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="activate", rowid=[build.version.id]),
            )
            self.assert200(response)
            self.assertIn(
                "Builds on version were successfully activated.",
                response.data.decode(),
            )
        db.session.expire_all()
        self.assertTrue(db.session.get(Build, build.id).active)

    def test_action_activate_multi(self):
        build1 = BuildFactory(active=False)
        build2 = BuildFactory(active=False)
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(
                    action="activate",
                    rowid=[build1.version.id, build2.version.id],
                ),
            )
            self.assert200(response)
            self.assertIn(
                "Builds have been successfully activated for 2 versions.",
                response.data.decode(),
            )
        db.session.expire_all()
        self.assertTrue(db.session.get(Build, build1.id).active)
        self.assertTrue(db.session.get(Build, build2.id).active)

    def test_action_deactivate_one(self):
        build = BuildFactory(active=True)
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="deactivate", rowid=[build.version.id]),
            )
            self.assert200(response)
            self.assertIn(
                "Builds on version were successfully deactivated.",
                response.data.decode(),
            )
        db.session.expire_all()
        self.assertFalse(db.session.get(Build, build.id).active)

    def test_action_deactivate_multi(self):
        build1 = BuildFactory(active=True)
        build2 = BuildFactory(active=True)
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(
                    action="deactivate",
                    rowid=[build1.version.id, build2.version.id],
                ),
            )
            self.assert200(response)
            self.assertIn(
                "Builds have been successfully deactivated for 2 versions.",
                response.data.decode(),
            )
        db.session.expire_all()
        self.assertFalse(db.session.get(Build, build1.id).active)
        self.assertFalse(db.session.get(Build, build2.id).active)

    def test_action_resync_info_allowed_for_package_admin(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.version.id]),
            )
        self.assert200(response)
        self.assertIn("refreshed", response.data.decode())

    def test_action_resync_info_blocked_for_developer(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("developer") as user:
            build.version.package.maintainers.append(user)
            db.session.commit()
            response = self.client.post(
                url_for("version.action_view"),
                data=dict(action="resync_info", rowid=[build.version.id]),
            )
        self.assert403(response)

    def test_action_resync_file_allowed_for_package_admin(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("version.action_view"),
                follow_redirects=True,
                data=dict(action="resync_file", rowid=[build.version.id]),
            )
        self.assert200(response)
        self.assertIn("refreshed", response.data.decode())

    def test_action_resync_file_blocked_for_developer(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("developer") as user:
            build.version.package.maintainers.append(user)
            db.session.commit()
            response = self.client.post(
                url_for("version.action_view"),
                data=dict(action="resync_file", rowid=[build.version.id]),
            )
        self.assert403(response)


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

    def test_action_deactivate_one(self):
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

    def test_action_resync_info_visible_to_package_admin(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("build.index_view"))
            self.assert200(response)
            self.assertIn("Resync Info", response.data.decode())

    def test_action_resync_info_requires_admin_or_package_admin(self):
        with self.logged_user("developer"):
            response = self.client.get(url_for("build.index_view"))
            self.assert200(response)
            self.assertNotIn("Resync Info", response.data.decode())

    def test_action_resync_info_refreshes_version_metadata(self):
        build = BuildFactory()
        db.session.commit()

        original_display = build.version.displaynames["enu"].displayname
        build.version.displaynames["enu"].displayname = "Altered"
        db.session.commit()

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.id]),
            )
            self.assert200(response)
            self.assertIn("refreshed", response.data.decode())

        db.session.expire_all()
        refreshed_build = db.session.get(Build, build.id)
        self.assertEqual(
            refreshed_build.version.displaynames["enu"].displayname,
            original_display,
        )

    def test_action_resync_info_refreshes_build_metadata(self):
        build = BuildFactory()
        db.session.commit()

        original_architectures = sorted(arch.code for arch in build.architectures)
        build.architectures = []
        db.session.commit()

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.id]),
            )
            self.assert200(response)
            self.assertIn("refreshed", response.data.decode())

        db.session.expire_all()
        refreshed_build = db.session.get(Build, build.id)
        self.assertEqual(
            sorted(arch.code for arch in refreshed_build.architectures),
            original_architectures,
        )

    def test_action_resync_info_single_build_no_siblings_succeeds(self):
        # A build with no siblings must resync cleanly.
        build = BuildFactory()
        db.session.commit()
        self.assertEqual(len(build.version.builds), 1)
        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.id]),
            )
        self.assert200(response)
        self.assertIn("refreshed", response.data.decode())

    def test_action_resync_info_invalidates_cache(self):
        build = BuildFactory()
        db.session.commit()
        from spkrepo.ext import cache as app_cache

        app_cache.set("packages_versions", "stale")
        with self.logged_user("package_admin", "admin"):
            self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.id]),
            )
        self.assertIsNone(app_cache.get("packages_versions"))

    def test_action_resync_file_invalidates_cache(self):
        build = BuildFactory()
        db.session.commit()
        from spkrepo.ext import cache as app_cache

        app_cache.set("packages_versions", "stale")
        with self.logged_user("package_admin", "admin"):
            self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_file", rowid=[build.id]),
            )
        self.assertIsNone(app_cache.get("packages_versions"))

    def test_action_resync_info_rejects_inconsistent_sibling_build(self):
        # Resyncing a single build must fail if its sibling SPK has different
        # version-level metadata, to prevent last-write-wins corruption.
        build1 = BuildFactory()
        build2 = BuildFactory(version=build1.version)
        db.session.commit()

        # Build build2's info independently and set a displayname that is
        # guaranteed to differ from what build1's SPK contains on disk.
        # We must override both the bare and the suffixed key because create_info
        # emits both "displayname" and "displayname_enu".
        original_displayname = build1.version.displaynames["enu"].displayname
        modified_displayname = original_displayname + " SIBLING MODIFIED"

        info2 = create_info(build2)
        info2["displayname"] = modified_displayname
        info2["displayname_enu"] = modified_displayname

        spk2_path = os.path.join(current_app.config["DATA_PATH"], build2.path)
        with open(spk2_path, "wb") as f:
            with create_spk(build2, info=info2) as spk:
                f.write(spk.read())

        # Sanity check: build1's SPK on disk must still have the original name.
        from spkrepo.utils import SPK, extract_version_metadata
        import io as _io

        spk1_path = os.path.join(current_app.config["DATA_PATH"], build1.path)
        with _io.open(spk1_path, "rb") as f:
            meta1 = extract_version_metadata(SPK(f))
        with _io.open(spk2_path, "rb") as f:
            meta2 = extract_version_metadata(SPK(f))
        self.assertNotEqual(
            meta1["displaynames"],
            meta2["displaynames"],
            "Precondition failed: SPK files must differ before running resync",
        )

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build1.id]),
            )
        self.assert200(response)
        self.assertIn("Failed", response.data.decode())
        self.assertNotIn("refreshed", response.data.decode())

    def test_action_resync_file_visible_to_package_admin(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("build.index_view"))
            self.assert200(response)
            self.assertIn("Resync File", response.data.decode())

    def test_action_resync_file_requires_admin_or_package_admin(self):
        with self.logged_user("developer"):
            response = self.client.get(url_for("build.index_view"))
            self.assert200(response)
            self.assertNotIn("Resync File", response.data.decode())

    def test_action_resync_file_refreshes_single_build(self):
        build = BuildFactory()
        db.session.commit()

        build.md5 = None
        build.size = None
        db.session.commit()

        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_file", rowid=[build.id]),
            )
            self.assert200(response)
            self.assertIn("refreshed", response.data.decode())

        db.session.expire_all()
        refreshed_build = db.session.get(Build, build.id)
        self.assertEqual(refreshed_build.md5, refreshed_build.calculate_md5())
        self.assertIsNotNone(refreshed_build.size)
        self.assertGreater(refreshed_build.size, 0)

    def test_action_resync_info_allowed_for_package_admin(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_info", rowid=[build.id]),
            )
        self.assert200(response)
        self.assertIn("refreshed", response.data.decode())

    def test_action_resync_info_blocked_for_developer(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("developer") as user:
            build.version.package.maintainers.append(user)
            db.session.commit()
            response = self.client.post(
                url_for("build.action_view"),
                data=dict(action="resync_info", rowid=[build.id]),
            )
        self.assert403(response)

    def test_action_resync_file_allowed_for_package_admin(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="resync_file", rowid=[build.id]),
            )
        self.assert200(response)
        self.assertIn("refreshed", response.data.decode())

    def test_action_resync_file_blocked_for_developer(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("developer") as user:
            build.version.package.maintainers.append(user)
            db.session.commit()
            response = self.client.post(
                url_for("build.action_view"),
                data=dict(action="resync_file", rowid=[build.id]),
            )
        self.assert403(response)

    def test_action_unsign_skips_active_build(self):
        build = BuildFactory(active=True)
        db.session.commit()
        with self.logged_user("package_admin", "admin"):
            response = self.client.post(
                url_for("build.action_view"),
                follow_redirects=True,
                data=dict(action="unsign", rowid=[build.id]),
            )
        self.assert200(response)
        self.assertIn("must be deactivated before unsigning", response.data.decode())
        db.session.expire_all()
        self.assertTrue(db.session.get(Build, build.id).active)

    def test_action_sign_requires_admin(self):
        build = BuildFactory()
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("build.action_view"),
                data=dict(action="sign", rowid=[build.id]),
            )
        self.assert403(response)

    def test_action_unsign_requires_admin(self):
        build = BuildFactory(active=False)
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.post(
                url_for("build.action_view"),
                data=dict(action="unsign", rowid=[build.id]),
            )
        self.assert403(response)

    def test_developer_sees_only_maintainer_builds(self):
        # A developer who is a maintainer on a package sees only that package's builds.
        with self.logged_user("developer") as user:
            own_package = PackageFactory(maintainers=[user])
            BuildFactory(version__package=own_package)
            other_build = BuildFactory()
            db.session.commit()
            response = self.client.get(url_for("build.index_view"))
            self.assert200(response)
            response_data = response.data.decode()
            self.assertIn(own_package.name, response_data)
            self.assertNotIn(other_build.version.package.name, response_data)


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


class ScreenshotDeleteTestCase(BaseTestCase):
    def test_delete_removes_file(self):
        package = PackageFactory(add_screenshot=False)
        db.session.commit()
        with self.logged_user("package_admin"):
            self.client.post(
                url_for("screenshot.create_view"),
                data=dict(
                    package=str(package.id),
                    path=(create_image("Delete Test", 1280, 1024), "test.png"),
                ),
            )
            db.session.expire_all()
            self.assertEqual(len(package.screenshots), 1)
            screenshot = package.screenshots[0]
            screenshot_path = os.path.join(
                current_app.config["DATA_PATH"], screenshot.path
            )
            self.assertTrue(os.path.exists(screenshot_path))

            self.client.post(url_for("screenshot.delete_view", id=str(screenshot.id)))
        db.session.expire_all()
        self.assertEqual(len(package.screenshots), 0)
        self.assertFalse(os.path.exists(screenshot_path))
