# -*- coding: utf-8 -*-
import os
from unittest import TestLoader, TestSuite

from flask import current_app, url_for

from spkrepo.ext import db
from spkrepo.models import Package, Version
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
            self.client.get(url_for("admin.index")), url_for("security.login")
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
                response.data.decode(response.charset),
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
                response.data.decode(response.charset),
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
                response.data.decode(response.charset),
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
                response.data.decode(response.charset),
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
                response.data.decode(response.charset),
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
                response.data.decode(response.charset),
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
                response.data.decode(response.charset),
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
                response.data.decode(response.charset),
            )
            self.assertFalse(build1.active)
            self.assertFalse(build2.active)


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


def suite():
    suite = TestSuite()
    suite.addTest(TestLoader().loadTestsFromTestCase(IndexTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(UserTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(PackageTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(VersionTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(BuildTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(ScreenshotTestCase))
    return suite
