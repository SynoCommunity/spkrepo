# -*- coding: utf-8 -*-
import json
import os
from unittest import mock

from flask import current_app, url_for
from flask_security import url_for_security
from lxml.html import fromstring

from spkrepo.ext import db
from spkrepo.mail import SUPPRESSED_BOT_TEMPLATES, SpkrepoMailUtil
from spkrepo.models import Architecture
from spkrepo.models import Package as PackageModel
from spkrepo.models import user_datastore
from spkrepo.net import get_client_ip
from spkrepo.tests.common import (
    BaseTestCase,
    BuildFactory,
    PackageFactory,
    UserFactory,
    VersionFactory,
)
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
    def test_get_beta_hides_beta_label(self):
        active_build = BuildFactory(active=True)
        inactive_build = BuildFactory(active=False)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        response_data = response.data.decode()
        self.assertIn(
            active_build.version.displaynames["enu"].displayname,
            response_data,
        )
        self.assertIn(
            inactive_build.version.displaynames["enu"].displayname,
            response_data,
        )
        self.assertNotIn("beta", response_data)

    def test_get_no_packages(self):
        # Empty packages list renders 200 with no package entries.
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)

    def test_package_description_rendered(self):
        # The list page shows each package's (default build) description;
        # this exercises the dedicated default-description query.
        build = BuildFactory(active=True)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        self.assertIn(build.descriptions["enu"].description, response.data.decode())

    def test_active_only_has_no_archived_section(self):
        BuildFactory(active=True)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        self.assertNotIn("Archived Packages", response.data.decode())

    def test_inactive_package_appears_in_archived_section(self):
        build = BuildFactory(active=False)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        data = response.data.decode()
        self.assertIn("Archived Packages", data)
        self.assertIn(build.version.displaynames["enu"].displayname, data)

    def test_latest_versions_query_does_not_load_all_builds(self):
        # Regression guard for the packages-list query: it must not eager-load
        # every Build/Description (which joined firmware/architecture and was
        # ~700ms). Query count stays small and constant as builds grow.
        from sqlalchemy import event

        from spkrepo.views.frontend import _latest_versions_query

        for _ in range(5):
            BuildFactory(active=True)
        db.session.commit()

        statements = []

        def _record(conn, cursor, statement, parameters, context, executemany):
            statements.append(statement)

        event.listen(db.engine, "before_cursor_execute", _record)
        try:
            rows = _latest_versions_query(None)
        finally:
            event.remove(db.engine, "before_cursor_execute", _record)

        self.assertEqual(len(rows), 5)
        self.assertLessEqual(len(statements), 6, statements)
        joined = " ".join(statements).lower()
        self.assertNotIn("firmware", joined)
        self.assertNotIn("build_architecture", joined)

    def test_filtered_page_is_cached(self):
        BuildFactory(architectures=[Architecture.find("cedarview")], active=True)
        db.session.commit()
        with mock.patch(
            "spkrepo.views.frontend._latest_versions_query", return_value=[]
        ) as query:
            self.client.get(url_for("frontend.packages", arch="cedarview"))
            self.client.get(url_for("frontend.packages", arch="cedarview"))
        self.assertEqual(query.call_count, 1)

    def test_invalidate_packages_cache_clears_arch_variants(self):
        from spkrepo.views.frontend import invalidate_packages_cache

        BuildFactory(architectures=[Architecture.find("cedarview")], active=True)
        db.session.commit()
        # "noarch" is a valid filter value but not in the selectable
        # architecture list, so invalidation must not rely on enumerating it.
        for arch in ("cedarview", "noarch"):
            with self.subTest(arch=arch):
                with mock.patch(
                    "spkrepo.views.frontend._latest_versions_query", return_value=[]
                ) as query:
                    self.client.get(url_for("frontend.packages", arch=arch))
                    invalidate_packages_cache()
                    self.client.get(url_for("frontend.packages", arch=arch))
                self.assertEqual(query.call_count, 2)

    def test_filter_by_arch_shows_matching_hides_others(self):
        match = BuildFactory(
            architectures=[Architecture.find("cedarview")], active=True
        )
        other = BuildFactory(architectures=[Architecture.find("qoriq")], active=True)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages", arch="cedarview"))
        self.assert200(response)
        response_data = response.data.decode()
        self.assertIn(match.version.displaynames["enu"].displayname, response_data)
        self.assertNotIn(other.version.displaynames["enu"].displayname, response_data)
        self.assertIn("Showing packages for", response_data)
        # The clear-filter control is the hook the model/arch JS binds to; it
        # must be present (and absent when unfiltered) so "show all" can also
        # clear the remembered model.
        self.assertIn('id="showAllArch"', response_data)
        unfiltered = self.client.get(url_for("frontend.packages", arch="all"))
        self.assertNotIn('id="showAllArch"', unfiltered.data.decode())

    def test_filter_includes_noarch_builds(self):
        universal = BuildFactory(
            architectures=[Architecture.find("noarch")], active=True
        )
        db.session.commit()
        response = self.client.get(url_for("frontend.packages", arch="cedarview"))
        self.assert200(response)
        self.assertIn(
            universal.version.displaynames["enu"].displayname,
            response.data.decode(),
        )

    def test_filter_invalid_arch_returns_404(self):
        response = self.client.get(url_for("frontend.packages", arch="not-a-chip"))
        self.assert404(response)

    def test_filter_cookie_lifecycle(self):
        # Selecting via ?arch= persists in a cookie; arch=all clears it.
        match = BuildFactory(
            architectures=[Architecture.find("cedarview")], active=True
        )
        other = BuildFactory(architectures=[Architecture.find("qoriq")], active=True)
        db.session.commit()
        self.client.get(url_for("frontend.packages", arch="cedarview"))
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        response_data = response.data.decode()
        self.assertIn(match.version.displaynames["enu"].displayname, response_data)
        self.assertNotIn(other.version.displaynames["enu"].displayname, response_data)
        self.client.get(url_for("frontend.packages", arch="all"))
        response = self.client.get(url_for("frontend.packages"))
        self.assert200(response)
        self.assertNotIn("Showing packages for", response.data.decode())

    def test_filter_accepts_syno_spelling(self):
        # DSM/SRM spellings (e.g. 88f6281) resolve like nas.py does.
        match = BuildFactory(architectures=[Architecture.find("88f628x")], active=True)
        db.session.commit()
        response = self.client.get(url_for("frontend.packages", arch="88f6281"))
        self.assert200(response)
        self.assertIn(
            match.version.displaynames["enu"].displayname,
            response.data.decode(),
        )

    def test_filtered_card_links_carry_arch(self):
        # Card links keep ?arch= so the detail page stays filtered even
        # with cookies disabled.
        build = BuildFactory(
            architectures=[Architecture.find("cedarview")], active=True
        )
        db.session.commit()
        response = self.client.get(url_for("frontend.packages", arch="cedarview"))
        self.assert200(response)
        self.assertIn(
            url_for(
                "frontend.package",
                name=build.version.package.name,
                arch="cedarview",
            ),
            response.data.decode(),
        )


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

    def test_detail_filters_versions_by_arch(self):
        # Only versions with a matching build are shown when filtered.
        package = PackageFactory(name="multiversion-package")
        match = BuildFactory(
            version__package=package,
            version__version=1,
            architectures=[Architecture.find("cedarview")],
            active=True,
        )
        other = BuildFactory(
            version__package=package,
            version__version=2,
            architectures=[Architecture.find("qoriq")],
            active=True,
        )
        db.session.commit()
        response = self.client.get(
            url_for("frontend.package", name=package.name, arch="cedarview")
        )
        self.assert200(response)
        response_data = response.data.decode()
        self.assertIn(match.version.version_string, response_data)
        self.assertNotIn(other.version.version_string, response_data)

    def test_detail_filters_builds_within_version(self):
        # Non-matching builds of a shown version are hidden too.
        package = PackageFactory(name="multibuild-package")
        version = VersionFactory(package=package, version=1)
        BuildFactory(
            version=version,
            architectures=[Architecture.find("cedarview")],
            active=True,
        )
        BuildFactory(
            version=version,
            architectures=[Architecture.find("qoriq")],
            active=True,
        )
        db.session.commit()
        response = self.client.get(
            url_for("frontend.package", name=package.name, arch="cedarview")
        )
        self.assert200(response)
        response_data = response.data.decode()
        # NOTE: assert on badge markup, not bare codes — the debug
        # toolbar dumps the full architectures list into test responses.
        self.assertIn("cedarview</span>", response_data)
        self.assertNotIn("qoriq</span>", response_data)

    def test_detail_no_matching_build_returns_404(self):
        build = BuildFactory(architectures=[Architecture.find("qoriq")], active=True)
        db.session.commit()
        response = self.client.get(
            url_for(
                "frontend.package",
                name=build.version.package.name,
                arch="cedarview",
            )
        )
        self.assert404(response)


class ModelMapTestCase(BaseTestCase):
    def _load_mapping(self):
        path = os.path.join(current_app.static_folder, "data", "syno-models.json")
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def test_mapping_is_valid_json_with_spot_checks(self):
        mapping = self._load_mapping()
        models = {k: v for k, v in mapping.items() if not k.startswith("_")}
        self.assertGreater(len(models), 100)
        self.assertEqual(mapping["DS920+"], "geminilake")
        self.assertEqual(mapping["DS923+"], "r1000")
        self.assertEqual(mapping["DS1813+"], "cedarview")
        self.assertEqual(mapping["DS413"], "qoriq")
        # All mapped codes look like platform codenames.
        for model, arch in models.items():
            self.assertRegex(arch, r"^[a-z0-9]+$", f"bad arch for {model}")


class ProfileTestCase(BaseTestCase):
    def _get_api_key_form(self, response):
        # Locate the API key form by finding the form that contains the
        # api_key field, rather than assuming it is always forms[0].
        html = fromstring(response.data.decode())
        api_key_form = next((f for f in html.forms if "api_key" in f.fields), None)
        self.assertIsNotNone(api_key_form, "API key form not found in page")
        return api_key_form

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
            api_key_form = self._get_api_key_form(response)
            self.assertEqual(api_key_form.fields["api_key"], "")

    def test_post_generate_api_key_developer(self):
        with self.logged_user("developer", api_key=None):
            response = self.client.post(
                url_for("frontend.profile"), data=dict(), follow_redirects=True
            )
            self.assert200(response)
            api_key_form = self._get_api_key_form(response)
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
            api_key_form = self._get_api_key_form(response)
            # The logged developer user has a non-None api_key from the factory
            self.assertNotEqual(api_key_form.fields["api_key"], "")

    def test_post_generated_api_key_is_64_hex_chars(self):
        # generate_api_key() uses secrets.token_hex(32) → 64 hex characters.
        with self.logged_user("developer", api_key=None):
            response = self.client.post(
                url_for("frontend.profile"), data=dict(), follow_redirects=True
            )
            self.assert200(response)
            api_key_form = self._get_api_key_form(response)
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
        # Single adapter probe; trust-order branches live in domain units.
        with self.app.test_request_context(
            headers={
                "CF-Connecting-IP": "9.9.9.9",
                "X-Forwarded-For": "1.2.3.4, 5.6.7.8",
            }
        ):
            self.assertEqual(get_client_ip(), "1.2.3.4")


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
