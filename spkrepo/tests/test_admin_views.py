# -*- coding: utf-8 -*-
from flask import url_for

from spkrepo.tests.common import BaseTestCase


class ReferenceViewTestCase(BaseTestCase):
    # Architecture / Firmware / Service are near-identical reference list views.
    ENDPOINTS = (
        ("architecture.index_view", "Download Counts"),
        ("firmware.index_view", "Download Counts"),
        ("service.index_view", "apache-web"),
    )

    def test_anonymous(self):
        for endpoint, _ in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                self.assert403(self.client.get(url_for(endpoint)))

    def test_package_admin(self):
        for endpoint, _ in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                with self.logged_user("package_admin"):
                    self.assert200(self.client.get(url_for(endpoint)))

    def test_developer_blocked(self):
        for endpoint, _ in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                with self.logged_user("developer"):
                    self.assert403(self.client.get(url_for(endpoint)))

    def test_list_contains_expected(self):
        for endpoint, expected in self.ENDPOINTS:
            with self.subTest(endpoint=endpoint):
                with self.logged_user("package_admin"):
                    response = self.client.get(url_for(endpoint))
                    self.assert200(response)
                    self.assertIn(expected, response.data.decode())


class TaskStatusViewTestCase(BaseTestCase):
    def test_anonymous(self):
        response = self.client.get(url_for("tasks.index"))
        self.assert302(response)

    def test_package_admin(self):
        with self.logged_user("package_admin"):
            response = self.client.get(url_for("tasks.index"))
            self.assert200(response)
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
