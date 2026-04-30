# -*- coding: utf-8 -*-
from flask import url_for
from flask_security import url_for_security
from lxml.html import fromstring

from spkrepo.ext import db
from spkrepo.models import Package as PackageModel
from spkrepo.models import user_datastore
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
    # Beta packages appear on the Packages page but without a 'beta' label
    def test_get_active_beta_hides_beta_label(self):
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

    # Inactive beta packages still appear on the Packages page without a 'beta' label
    def test_get_inactive_beta_hides_beta_label(self):
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

    def test_get_no_packages(self):
        # Empty packages list renders 200 with no package entries.
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)


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

    def test_get_package_with_no_versions_returns_404(self):
        # A Package row that exists but has no versions should return 404.
        package = PackageModel(name="empty-package")
        db.session.add(package)
        db.session.commit()
        response = self.client.get(url_for("frontend.package", name="empty-package"))
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
            # Locate the API key form by finding the form that contains the
            # api_key field, rather than assuming it is always forms[0].
            api_key_form = next((f for f in html.forms if "api_key" in f.fields), None)
            self.assertIsNotNone(api_key_form, "API key form not found in page")
            self.assertEqual(api_key_form.fields["api_key"], "")

    def test_post_generate_api_key_developer(self):
        with self.logged_user("developer", api_key=None):
            response = self.client.post(
                url_for("frontend.profile"), data=dict(), follow_redirects=True
            )
            self.assert200(response)
            html = fromstring(response.data.decode())
            api_key_form = next((f for f in html.forms if "api_key" in f.fields), None)
            self.assertIsNotNone(api_key_form, "API key form not found in page")
            self.assertNotEqual(api_key_form.fields["api_key"], "")

    def test_post_generate_api_key_not_developer(self):
        with self.logged_user(api_key=None):
            response = self.client.post(url_for("frontend.profile"), data=dict())
            self.assert200(response)
            self.assertNotIn("API key", response.data.decode())

    def test_get_existing_api_key_prepopulated(self):
        # An existing API key should be pre-populated in the form field.
        with self.logged_user("developer"):
            response = self.client.get(url_for("frontend.profile"))
            self.assert200(response)
            html = fromstring(response.data.decode())
            api_key_form = next((f for f in html.forms if "api_key" in f.fields), None)
            self.assertIsNotNone(api_key_form, "API key form not found in page")
            # The logged developer user has a non-None api_key from the factory
            self.assertNotEqual(api_key_form.fields["api_key"], "")

    def test_post_generated_api_key_is_64_hex_chars(self):
        # generate_api_key() uses secrets.token_hex(32) → 64 hex characters.
        with self.logged_user("developer", api_key=None):
            response = self.client.post(
                url_for("frontend.profile"), data=dict(), follow_redirects=True
            )
            self.assert200(response)
            html = fromstring(response.data.decode())
            api_key_form = next((f for f in html.forms if "api_key" in f.fields), None)
            self.assertIsNotNone(api_key_form)
            api_key = api_key_form.fields["api_key"]
            self.assertRegex(
                api_key,
                r"^[0-9a-f]{64}$",
                "API key should be 64 lowercase hex characters",
            )


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

    def test_username_too_short(self):
        # Length(min=4) validator on SpkrepoRegisterForm.username
        data = dict(
            username="abc",
            email="short@gmail.com",
            password="password",
            password_confirm="password",
        )
        response = self.client.post(url_for_security("register"), data=data)
        self.assert200(response)
        self.assertNotIn("Logout", response.data.decode())

    def test_successful_registration(self):
        data = dict(
            username="newuser",
            email="newuser@gmail.com",
            password="password",
            password_confirm="password",
        )
        response = self.client.post(
            url_for_security("register"), data=data, follow_redirects=True
        )
        self.assert200(response)
        user = user_datastore.find_user(username="newuser")
        self.assertIsNotNone(user)
        self.assertEqual(user.email, "newuser@gmail.com")
