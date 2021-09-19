# -*- coding: utf-8 -*-
from unittest import TestLoader, TestSuite

from flask import url_for
from flask_security import url_for_security
from lxml.html import fromstring

from spkrepo.ext import db
from spkrepo.tests.common import BaseTestCase, BuildFactory, UserFactory


class IndexTestCase(BaseTestCase):
    def test_get_anonymous(self):
        response = self.client.get(url_for("frontend.index"))
        self.assert200(response)
        self.assertIn("Login", response.data.decode(response.charset))
        self.assertIn("Register", response.data.decode(response.charset))

    def test_get_logged_user(self):
        with self.logged_user():
            response = self.client.get(url_for("frontend.index"))
            self.assert200(response)
            self.assertIn("Logout", response.data.decode(response.charset))
            self.assertIn("Profile", response.data.decode(response.charset))


class PackagesTestCase(BaseTestCase):
    def test_get_active_stable(self):
        build = BuildFactory(version__report_url=None, active=True)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response.data.decode(response.charset),
        )
        self.assertNotIn("beta", response.data.decode(response.charset))

    def test_get_active_not_stable(self):
        build = BuildFactory(active=True)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response.data.decode(response.charset),
        )
        self.assertIn("beta", response.data.decode(response.charset))

    def test_get_not_active_not_stable(self):
        build = BuildFactory(active=False)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        self.assertNotIn(
            build.version.displaynames["enu"].displayname,
            response.data.decode(response.charset),
        )
        self.assertNotIn("beta", response.data.decode(response.charset))

    def test_get_not_active_stable(self):
        build = BuildFactory(active=False)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        self.assertNotIn(
            build.version.displaynames["enu"].displayname,
            response.data.decode(response.charset),
        )
        self.assertNotIn("beta", response.data.decode(response.charset))


class PackageTestCase(BaseTestCase):
    def test_get(self):
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
        for a in build.architectures:
            self.assertIn(a.code, response.data.decode(response.charset))
        self.assertIn(
            build.version.displaynames["enu"].displayname,
            response.data.decode(response.charset),
        )
        self.assertIn(
            build.version.descriptions["enu"].description,
            response.data.decode(response.charset),
        )

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
            self.assertNotIn("API key", response.data.decode(response.charset))

    def test_get_developer(self):
        with self.logged_user("developer"):
            response = self.client.get(url_for("frontend.profile"))
            self.assert200(response)
            self.assertIn("API key", response.data.decode(response.charset))

    def test_get_no_api_key_by_default(self):
        with self.logged_user("developer", api_key=None):
            response = self.client.get(url_for("frontend.profile"))
            html = fromstring(response.data.decode(response.charset))
            self.assertTrue(html.forms[0].fields["api_key"] == "")

    def test_post_generate_api_key_developer(self):
        with self.logged_user("developer", api_key=None):
            response = self.client.post(
                url_for("frontend.profile"), data=dict(), follow_redirects=True
            )
            self.assert200(response)
            html = fromstring(response.data.decode(response.charset))
            self.assertTrue(html.forms[0].fields["api_key"] != "")

    def test_post_generate_api_key_not_developer(self):
        with self.logged_user(api_key=None):
            response = self.client.post(url_for("frontend.profile"), data=dict())
            self.assert200(response)


class RegisterTestCase(BaseTestCase):
    def test_unique_user_username(self):
        data = dict(
            username="test",
            email="test@test.com",
            password="password",
            password_confirm="password",
        )
        self.client.post(url_for_security("register"), data=data)
        response = self.client.post(url_for_security("register"), data=data)
        self.assertIn("Username already taken", response.data.decode(response.charset))


def suite():
    suite = TestSuite()
    suite.addTest(TestLoader().loadTestsFromTestCase(IndexTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(PackagesTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(PackageTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(ProfileTestCase))
    suite.addTest(TestLoader().loadTestsFromTestCase(RegisterTestCase))
    return suite
