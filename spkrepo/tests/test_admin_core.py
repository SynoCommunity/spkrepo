# -*- coding: utf-8 -*-
import os
from unittest.mock import patch

from flask import current_app, url_for

from spkrepo.ext import db
from spkrepo.models import Package
from spkrepo.tests.common import BaseTestCase, PackageFactory, create_image
from spkrepo.views.tasks import resync_build_file, resync_build_metadata


def _run_task_sync(task_func):
    """Return a mock for .delay() that runs the task synchronously in-process.

    Usage:
        with patch_resync_info(), patch_resync_file():
            ...

    The mock captures the build_id and build_label arguments that the action
    handler passes to .delay() and calls the underlying task function directly,
    so DB state is updated before assertions run — no broker needed.
    """

    def fake_delay(build_id, build_label=""):
        task_func(build_id, build_label)

        class FakeResult:
            id = "fake-task-id"

        return FakeResult()

    return fake_delay


def patch_resync_info():
    return patch.object(
        resync_build_metadata,
        "delay",
        side_effect=_run_task_sync(resync_build_metadata.run),
    )


def patch_resync_file():
    return patch.object(
        resync_build_file, "delay", side_effect=_run_task_sync(resync_build_file.run)
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
