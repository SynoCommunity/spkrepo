# -*- coding: utf-8 -*-
import re

from flask import url_for

from spkrepo.ext import db
from spkrepo.models import Role
from spkrepo.tests.common import BaseTestCase, PackageFactory, UserFactory


def _select_values(html, name):
    """Return the integer option values of the <select name="...">."""
    match = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', html, re.S)
    if not match:
        return set()
    return {int(v) for v in re.findall(r'<option[^>]*value="(\d+)"', match.group(1))}


class PackageFormChoicesTestCase(BaseTestCase):
    def test_author_and_maintainer_choices_are_role_scoped(self):
        """Author lists only package_admins; maintainers only developers."""
        admin_only = UserFactory(
            username="zz_admin_only", roles=[Role.find("package_admin")]
        )
        dev_only = UserFactory(username="zz_dev_only", roles=[Role.find("developer")])
        both = UserFactory(
            username="zz_both",
            roles=[Role.find("package_admin"), Role.find("developer")],
        )
        no_roles = UserFactory(username="zz_no_roles")
        package = PackageFactory(
            name="zz_choices_pkg", author=admin_only, maintainers=[dev_only]
        )
        db.session.commit()

        with self.logged_user("package_admin"):
            responses = {
                "create": self.client.get(url_for("package.create_view")),
                "edit": self.client.get(
                    url_for("package.edit_view", id=str(package.id))
                ),
            }

        for label, response in responses.items():
            self.assert200(response)
            body = response.data.decode()
            authors = _select_values(body, "author")
            maintainers = _select_values(body, "maintainers")
            self.assertIn(admin_only.id, authors, label)
            self.assertIn(both.id, authors, label)
            self.assertNotIn(dev_only.id, authors, label)
            self.assertNotIn(no_roles.id, authors, label)
            self.assertIn(dev_only.id, maintainers, label)
            self.assertIn(both.id, maintainers, label)
            self.assertNotIn(admin_only.id, maintainers, label)
            self.assertNotIn(no_roles.id, maintainers, label)


class UserDefaultSortTestCase(BaseTestCase):
    def test_default_sort_active_first_then_username(self):
        # Users default to active (desc) then username (asc).
        UserFactory(username="zzzsortzeta", active=True)
        UserFactory(username="aaasortalpha", active=True)
        UserFactory(username="mmmsortmike", active=False)
        db.session.commit()
        with self.logged_user("admin"):
            response = self.client.get(url_for("user.index_view"))
        self.assert200(response)
        data = response.data.decode()
        self.assertLess(data.index("aaasortalpha"), data.index("zzzsortzeta"))
        self.assertLess(data.index("zzzsortzeta"), data.index("mmmsortmike"))


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
