# -*- coding: utf-8 -*-
from unittest import mock

from flask import url_for
from flask_security import url_for_security
from lxml.html import fromstring

from spkrepo.ext import db
from spkrepo.mail import SUPPRESSED_BOT_TEMPLATES, SpkrepoMailUtil
from spkrepo.models import Package as PackageModel
from spkrepo.models import user_datastore
from spkrepo.net import get_client_ip
from spkrepo.tests.common import BaseTestCase, BuildFactory, UserFactory
from spkrepo.views.frontend import _verify_turnstile_token


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
    def _assert_package_page(self, active, is_stable):
        kwargs = dict(
            version__package__author=UserFactory(),
            active=active,
        )
        if is_stable:
            kwargs["version__report_url"] = None
        build = BuildFactory(**kwargs)
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
            build.descriptions["enu"].description,
            response_data,
        )
        if is_stable:
            self.assertNotIn("beta", response_data)
        else:
            self.assertIn("beta", response_data)
        if active:
            self.assertIn("badge badge-success", response_data)
            self.assertNotIn("Inactive: Manual installation only.", response_data)
        else:
            self.assertIn("badge badge-secondary", response_data)
            self.assertIn("Inactive: Manual installation only.", response_data)

    def test_get_active_stable(self):
        self._assert_package_page(active=True, is_stable=True)

    def test_get_not_active_stable(self):
        self._assert_package_page(active=False, is_stable=True)

    def test_get_active_not_stable(self):
        self._assert_package_page(active=True, is_stable=False)

    def test_get_not_active_not_stable(self):
        self._assert_package_page(active=False, is_stable=False)

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

    def test_unique_user_username_no_enumeration(self):
        # Registering an already-taken username must NOT reveal that it exists
        # (SECURITY_RETURN_GENERIC_RESPONSES) — the response is the same
        # generic redirect as a successful submission.
        data = dict(
            username="test",
            email="test@gmail.com",
            password="password",
            password_confirm="password",
        )
        self.client.post(url_for_security("register"), data=data)
        response = self.client.post(url_for_security("register"), data=data)
        self.assertNotIn("Username already taken", response.data.decode())
        self.assertNotIn("Email already registered", response.data.decode())

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

    def test_honeypot_rejects_bot(self):
        # A filled honeypot field means an automated bot — the submitted
        # registration must be rejected and no user created.
        data = dict(
            username="botuser",
            email="bot@gmail.com",
            password="password",
            password_confirm="password",
            website="http://spam.example.com",
        )
        self.client.post(url_for_security("register"), data=data)
        self.assertIsNone(user_datastore.find_user(username="botuser"))


class TurnstileTestCase(BaseTestCase):
    def test_no_turnstile_id_collision(self):
        # Regression guard: browsers expose every id as a window global, so
        # an element with id="turnstile" would shadow window.turnstile and
        # stop the Cloudflare library from initializing ("already loaded").
        response = self.client.get(url_for_security("register"))
        self.assert200(response)
        self.assertNotIn('id="turnstile"', response.data.decode())

    def _enable_enforcement(self):
        # Flip off the TESTING bypass so server-side verification actually
        # runs (CSRF stays disabled, mail stays suppressed).
        self.app.config["TESTING"] = False
        self.app.config["MAIL_SUPPRESS_SEND"] = True
        self.app.config["TURNSTILE_SECRET_KEY"] = "test-secret"

    def _disable_enforcement(self):
        self.app.config["TESTING"] = True

    def test_verify_token_success(self):
        self.app.config["TURNSTILE_SECRET_KEY"] = "test-secret"
        try:
            with mock.patch("spkrepo.views.frontend.requests.post") as mock_post:
                mock_post.return_value.json.return_value = {"success": True}
                with self.app.test_request_context():
                    self.assertTrue(_verify_turnstile_token("tok", "127.0.0.1"))
                mock_post.assert_called_once()
        finally:
            del self.app.config["TURNSTILE_SECRET_KEY"]

    def test_verify_token_failure(self):
        self.app.config["TURNSTILE_SECRET_KEY"] = "test-secret"
        try:
            with mock.patch("spkrepo.views.frontend.requests.post") as mock_post:
                mock_post.return_value.json.return_value = {"success": False}
                with self.app.test_request_context():
                    self.assertFalse(_verify_turnstile_token("tok", "127.0.0.1"))
        finally:
            del self.app.config["TURNSTILE_SECRET_KEY"]

    def test_verify_token_request_error(self):
        import requests as requests_module

        self.app.config["TURNSTILE_SECRET_KEY"] = "test-secret"
        try:
            with mock.patch(
                "spkrepo.views.frontend.requests.post",
                side_effect=requests_module.ConnectionError("down"),
            ):
                with self.app.test_request_context():
                    self.assertFalse(_verify_turnstile_token("tok", "127.0.0.1"))
        finally:
            del self.app.config["TURNSTILE_SECRET_KEY"]

    def test_verify_token_missing_secret(self):
        with self.app.test_request_context():
            self.assertFalse(_verify_turnstile_token("tok", "127.0.0.1"))

    def test_verify_token_hostname_match(self):
        self.app.config["TURNSTILE_SECRET_KEY"] = "test-secret"
        self.app.config["TURNSTILE_HOSTNAME"] = "example.com"
        try:
            with mock.patch("spkrepo.views.frontend.requests.post") as mock_post:
                mock_post.return_value.json.return_value = {
                    "success": True,
                    "hostname": "example.com",
                }
                with self.app.test_request_context():
                    self.assertTrue(_verify_turnstile_token("tok", "127.0.0.1"))
        finally:
            del self.app.config["TURNSTILE_SECRET_KEY"]
            del self.app.config["TURNSTILE_HOSTNAME"]

    def test_verify_token_hostname_mismatch(self):
        # Token minted for a different site must be rejected.
        self.app.config["TURNSTILE_SECRET_KEY"] = "test-secret"
        self.app.config["TURNSTILE_HOSTNAME"] = "example.com"
        try:
            with mock.patch("spkrepo.views.frontend.requests.post") as mock_post:
                mock_post.return_value.json.return_value = {
                    "success": True,
                    "hostname": "evil.example.com",
                }
                with self.app.test_request_context():
                    self.assertFalse(_verify_turnstile_token("tok", "127.0.0.1"))
        finally:
            del self.app.config["TURNSTILE_SECRET_KEY"]
            del self.app.config["TURNSTILE_HOSTNAME"]

    def test_registration_blocked_without_token(self):
        # Fail-closed: no cf-turnstile-response token, no user created.
        self._enable_enforcement()
        try:
            data = dict(
                username="notabot",
                email="notabot@gmail.com",
                password="password",
                password_confirm="password",
            )
            response = self.client.post(url_for_security("register"), data=data)
            self.assertIn("Bot verification failed", response.data.decode())
            self.assertIsNone(user_datastore.find_user(username="notabot"))
        finally:
            self._disable_enforcement()

    def test_registration_succeeds_with_valid_token(self):
        with mock.patch("spkrepo.views.frontend.requests.post") as mock_post:
            mock_post.return_value.json.return_value = {"success": True}
            self._enable_enforcement()
            try:
                data = dict(
                    username="realuser",
                    email="realuser@gmail.com",
                    password="password",
                    password_confirm="password",
                    **{"cf-turnstile-response": "valid-token"},
                )
                self.client.post(url_for_security("register"), data=data)
                user = user_datastore.find_user(username="realuser")
                self.assertIsNotNone(user)
                self.assertEqual(user.email, "realuser@gmail.com")
            finally:
                self._disable_enforcement()


class BotMailSuppressionTestCase(BaseTestCase):
    def test_duplicate_registration_sends_no_mail(self):
        # Second registration with an already-taken email must not send any
        # mail (suppressed bot template), while keeping the generic response.
        data = dict(
            username="dupuser",
            email="dupuser@gmail.com",
            password="password",
            password_confirm="password",
        )
        self.client.post(url_for_security("register"), data=data)
        with mock.patch("flask_security.MailUtil.send_mail") as mock_send:
            with self.assertLogs("spkrepo.mail", level="WARNING") as logs:
                response = self.client.post(url_for_security("register"), data=data)
        mock_send.assert_not_called()
        self.assertTrue(
            any("Suppressed bot registration email" in line for line in logs.output)
        )
        self.assertNotIn("Email already registered", response.data.decode())

    def test_taken_username_sends_no_mail(self):
        # New email + taken username: the stranger-directed notice must be
        # suppressed as well.
        data = dict(
            username="takenname",
            email="takenname@gmail.com",
            password="password",
            password_confirm="password",
        )
        self.client.post(url_for_security("register"), data=data)
        retry = dict(
            username="takenname",
            email="other@gmail.com",
            password="password",
            password_confirm="password",
        )
        with mock.patch("flask_security.MailUtil.send_mail") as mock_send:
            with self.assertLogs("spkrepo.mail", level="WARNING"):
                self.client.post(url_for_security("register"), data=retry)
        mock_send.assert_not_called()

    def test_legit_templates_still_send(self):
        # Non-bot templates must delegate to the parent implementation.
        util = SpkrepoMailUtil(app=None)
        with mock.patch("flask_security.MailUtil.send_mail") as mock_send:
            util.send_mail(
                "welcome", "Welcome", "new@gmail.com", "sender@x.com", "body", None
            )
        mock_send.assert_called_once()
        for template in SUPPRESSED_BOT_TEMPLATES:
            with mock.patch("flask_security.MailUtil.send_mail") as mock_send:
                util.send_mail(
                    template, "Welcome", "x@y.com", "sender@x.com", "body", None
                )
            mock_send.assert_not_called()


class GetClientIpTestCase(BaseTestCase):
    def test_cf_connecting_ip_ignored(self):
        # Cloudflare is DNS-only here, so this header can never arrive
        # legitimately — it must not be trusted (rate-limit bypass).
        with self.app.test_request_context(
            headers={
                "CF-Connecting-IP": "9.9.9.9",
                "X-Forwarded-For": "1.2.3.4, 5.6.7.8",
            }
        ):
            self.assertEqual(get_client_ip(), "1.2.3.4")

    def test_fastly_client_ip(self):
        # Set by Fastly to its connecting client; beats XFF parsing.
        with self.app.test_request_context(
            headers={
                "Fastly-Client-IP": "8.8.8.8",
                "X-Forwarded-For": "1.2.3.4, 5.6.7.8",
            }
        ):
            self.assertEqual(get_client_ip(), "8.8.8.8")

    def test_second_to_last_forwarded_for_entry(self):
        # Fastly appends the real client, nginx appends its peer; anything
        # left of those two is client-spoofable.
        with self.app.test_request_context(
            headers={"X-Forwarded-For": "1.2.3.4, 5.6.7.8"}
        ):
            self.assertEqual(get_client_ip(), "1.2.3.4")

    def test_single_forwarded_for_entry(self):
        # Direct-to-nginx traffic: the lone entry is nginx's peer.
        with self.app.test_request_context(headers={"X-Forwarded-For": "5.6.7.8"}):
            self.assertEqual(get_client_ip(), "5.6.7.8")

    def test_remote_addr_fallback(self):
        with self.app.test_request_context(environ_base={"REMOTE_ADDR": "10.0.0.1"}):
            self.assertEqual(get_client_ip(), "10.0.0.1")


class RateLimitTestCase(BaseTestCase):
    def test_register_rate_limited(self):
        # 10/hour per IP: the 11th POST to the register endpoint is refused
        # with 429 while earlier ones go through.
        data = dict(
            username="ratelimituser",
            email="ratelimit@gmail.com",
            password="password",
            password_confirm="password",
        )
        for _ in range(10):
            response = self.client.post(url_for_security("register"), data=data)
            self.assertNotEqual(response.status_code, 429)
        response = self.client.post(url_for_security("register"), data=data)
        self.assertEqual(response.status_code, 429)

    def test_other_endpoints_unaffected(self):
        # Breaching the register limit must not spill over to other routes.
        data = dict(
            username="otheruser",
            email="other@gmail.com",
            password="password",
            password_confirm="password",
        )
        for _ in range(11):
            self.client.post(url_for_security("register"), data=data)
        response = self.client.get(url_for("frontend.index"))
        self.assert200(response)
