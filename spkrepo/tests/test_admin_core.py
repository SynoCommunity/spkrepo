# -*- coding: utf-8 -*-
import os

from flask import current_app, url_for

from spkrepo.ext import db
from spkrepo.models import Package
from spkrepo.tests.common import (
    BaseTestCase,
    BuildFactory,
    DownloadStatFactory,
    PackageFactory,
    create_image,
)


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
        self.assertEqual(len(db.session.execute(db.select(Package)).scalars().all()), 0)
        with self.logged_user("package_admin"):
            self.client.post(url_for("package.create_view"), data=dict(name="test"))
        self.assertEqual(len(db.session.execute(db.select(Package)).scalars().all()), 1)
        package = db.session.execute(db.select(Package)).scalars().one()
        package_path = os.path.join(current_app.config["DATA_PATH"], package.name)
        self.assertTrue(os.path.exists(package_path))

    def test_on_model_delete(self):
        package = PackageFactory()
        db.session.commit()
        self.assertEqual(len(db.session.execute(db.select(Package)).scalars().all()), 1)
        package_path = os.path.join(current_app.config["DATA_PATH"], package.name)
        self.assertTrue(os.path.exists(package_path))
        with self.logged_user("package_admin", "admin"):
            self.client.post(url_for("package.delete_view", id=str(package.id)))
        self.assertEqual(len(db.session.execute(db.select(Package)).scalars().all()), 0)
        self.assertTrue(not os.path.exists(package_path))


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


class IndexTestCase(BaseTestCase):
    def test_anonymous_redirects_to_login(self):
        response = self.client.get(url_for("admin.index"), follow_redirects=False)
        self.assert302(response)
        self.assertRedirectsTo(response, url_for("security.login"))

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

    def test_renders_download_charts(self):
        """The index charts aggregate real download stats for privileged users."""
        build = BuildFactory()
        DownloadStatFactory(build=build, count=987654)
        db.session.commit()
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("admin.index"))
        self.assert200(response)
        self.assertIn(b"987654", response.data)

    def test_renders_charts_for_developer(self):
        """The maintainer-scoped chart queries run for non-privileged users."""
        build = BuildFactory()
        DownloadStatFactory(build=build, count=987654)
        db.session.commit()
        with self.logged_user("developer"):
            response = self.client.get(url_for("admin.index"))
        self.assert200(response)
