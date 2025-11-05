# -*- coding: utf-8 -*-

from flask import url_for
from flask_security import url_for_security
from lxml.html import fromstring

from spkrepo.ext import db
from spkrepo.tests.common import BaseTestCase, BuildFactory, UserFactory


class IndexTestCase(BaseTestCase):
    def test_get_anonymous(self):
        response = self.client.get(url_for("frontend.index"))
        self.assert200(response)
        response_data = response.data.decode()
        self.assertIn("Login", response_data)
        self.assertIn("Register", response_data)

    def test_get_logged_user(self):
        with self.logged_user():
            response = self.client.get(url_for("frontend.index"))
            self.assert200(response)
            response_data = response.data.decode()
            self.assertIn("Logout", response_data)
            self.assertIn("Profile", response_data)


class PackagesTestCase(BaseTestCase):
    # Assert beta is not shown on Packages page
    def test_get_active_not_stable(self):
        build = BuildFactory(active=True)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        response_data = response.data.decode()
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response_data,
        )
        self.assertNotIn("beta", response_data)

    # Assert package with only inactive version(s) is shown on Packages page
    def test_get_not_active_not_stable(self):
        build = BuildFactory(active=False)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        response_data = response.data.decode()
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response_data,
        )
        self.assertNotIn("beta", response_data)


class PackageTestCase(BaseTestCase):
    def test_get_active_stable(self):
        build = BuildFactory(
            version__package__author=UserFactory(),
            version__report_url=None,
            active=True,
        )
        db.session.commit()
        response = self.client.get(
            url_for("frontend.package", name=build.version.package.name)
        )
        self.assert200(response)
        response_data = response.data.decode()
        for a in build.architectures:
            self.assertIn(a.code, response_data)
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response_data,
        )
        self.assertIn(
            build.version.descriptions["enu"].description,
            response_data,
        )
        self.assertNotIn("beta", response_data)
        self.assertIn("label label-success", response_data)

    def test_get_not_active_stable(self):
        build = BuildFactory(
            version__package__author=UserFactory(),
            version__report_url=None,
            active=False,
        )
        db.session.commit()
        response = self.client.get(
            url_for("frontend.package", name=build.version.package.name)
        )
        self.assert200(response)
        response_data = response.data.decode()
        for a in build.architectures:
            self.assertIn(a.code, response_data)
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response_data,
        )
        self.assertIn(
            build.version.descriptions["enu"].description,
            response_data,
        )
        self.assertNotIn("beta", response_data)
        self.assertIn("label label-default", response_data)

    def test_get_active_not_stable(self):
        build = BuildFactory(
            version__package__author=UserFactory(),
            active=True,
        )
        db.session.commit()
        response = self.client.get(
            url_for("frontend.package", name=build.version.package.name)
        )
        self.assert200(response)
        response_data = response.data.decode()
        for a in build.architectures:
            self.assertIn(a.code, response_data)
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response_data,
        )
        self.assertIn(
            build.version.descriptions["enu"].description,
            response_data,
        )
        self.assertIn("beta", response_data)
        self.assertIn("label label-success", response_data)

    def test_get_not_active_not_stable(self):
        build = BuildFactory(
            version__package__author=UserFactory(),
            active=False,
        )
        db.session.commit()
        response = self.client.get(
            url_for("frontend.package", name=build.version.package.name)
        )
        self.assert200(response)
        response_data = response.data.decode()
        for a in build.architectures:
            self.assertIn(a.code, response_data)
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response_data,
        )
        self.assertIn(
            build.version.descriptions["enu"].description,
            response_data,
        )
        self.assertIn("beta", response_data)
        self.assertIn("label label-default", response_data)
        self.assertIn("Inactive: Manual installation only.", response_data)

    def test_get_no_package(self):
        response = self.client.get(url_for("frontend.package", name="no-package"))
        self.assert404(response)


class ProfileTestCase(BaseTestCase):
    def test_get_anonymous(self):
        self.assert302(self.client.get(url_for("frontend.profile")))

    def test_get_user(self):
        with self.logged_user():
            response = self.client.get(url_for("frontend.profile"))
            self.assert200(response)
            self.assertNotIn("API key", response.data.decode())

    def test_get_developer(self):
        with self.logged_user("developer"):
            response = self.client.get(url_for("frontend.profile"))
            self.assert200(response)
            self.assertIn("API key", response.data.decode())

    def test_get_no_api_key_by_default(self):
        with self.logged_user("developer", api_key=None):
            response = self.client.get(url_for("frontend.profile"))
            html = fromstring(response.data.decode())
            self.assertTrue(html.forms[0].fields["api_key"] == "")

    def test_post_generate_api_key_developer(self):
        with self.logged_user("developer", api_key=None):
            response = self.client.post(
                url_for("frontend.profile"), data=dict(), follow_redirects=True
            )
            self.assert200(response)
            html = fromstring(response.data.decode())
            self.assertTrue(html.forms[0].fields["api_key"] != "")

    def test_post_generate_api_key_not_developer(self):
        with self.logged_user(api_key=None):
            response = self.client.post(url_for("frontend.profile"), data=dict())
            self.assert200(response)


class RegisterTestCase(BaseTestCase):
    def test_invalid_email(self):
        data = dict(
            username="test",
            email="test@localhost",
            password="password",
            password_confirm="password",
        )
        response = self.client.post(url_for_security("register"), data=data)
        self.assertIn("Invalid email address", response.data.decode())

    def test_unique_user_username(self):
        data = dict(
            username="test",
            email="test@gmail.com",
            password="password",
            password_confirm="password",
        )
        self.client.post(url_for_security("register"), data=data)
        response = self.client.post(url_for_security("register"), data=data)
        self.assertIn("Username already taken", response.data.decode())
