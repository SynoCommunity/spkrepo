# -*- coding: utf-8 -*-
from unittest.mock import patch

from flask import url_for

from spkrepo.tests.common import (
    BaseTestCase,
)
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


class ArchitectureViewTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert403(self.client.get(url_for("architecture.index_view")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("architecture.index_view")))

    def test_developer_blocked(self):
        with self.logged_user("developer"):
            self.assert403(self.client.get(url_for("architecture.index_view")))

    def test_list_contains_architectures(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("architecture.index_view"))
            self.assert200(response)
            self.assertIn("Download Counts", response.data.decode())


class FirmwareViewTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert403(self.client.get(url_for("firmware.index_view")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("firmware.index_view")))

    def test_developer_blocked(self):
        with self.logged_user("developer"):
            self.assert403(self.client.get(url_for("firmware.index_view")))

    def test_list_contains_firmware(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("firmware.index_view"))
            self.assert200(response)
            self.assertIn("Download Counts", response.data.decode())


class ServiceViewTestCase(BaseTestCase):
    def test_anonymous(self):
        self.assert403(self.client.get(url_for("service.index_view")))

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("service.index_view")))

    def test_developer_blocked(self):
        with self.logged_user("developer"):
            self.assert403(self.client.get(url_for("service.index_view")))

    def test_list_contains_services(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("service.index_view"))
            self.assert200(response)
            self.assertIn("apache-web", response.data.decode())


class TaskStatusViewTestCase(BaseTestCase):
    def test_anonymous(self):
        response = self.client.get(url_for("tasks.index"))
        self.assert302(response)

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            self.assert200(self.client.get(url_for("tasks.index")))
            response = self.client.get(url_for("tasks.index"))
            self.assertIn("Task Status", response.data.decode())

    def test_developer(self):
        with self.logged_user("developer"):
            self.assert200(self.client.get(url_for("tasks.index")))

    def test_user_blocked(self):
        with self.logged_user():
            response = self.client.get(url_for("tasks.index"))
            self.assert302(response)

    def test_status_json_returns_empty_list(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("tasks.status_json"))
            self.assert200(response)
            data = response.get_json()
            self.assertEqual(data["tasks"], [])
            self.assertEqual(data["pending_count"], 0)

    def test_status_json_redirects_for_anonymous(self):
        response = self.client.get(url_for("tasks.status_json"))
        self.assert302(response)

    def test_clear_redirects_when_no_tasks(self):
        with self.logged_user("package_admin"):
            response = self.client.post(url_for("tasks.clear"), follow_redirects=True)
            self.assert200(response)

    def test_clear_redirects_for_anonymous(self):
        response = self.client.post(url_for("tasks.clear"))
        self.assert302(response)
