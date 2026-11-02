# -*- coding: utf-8 -*-
"""CLI commands: user creation and the destructive DB/filesystem commands."""

import os
import shutil
import tempfile

from flask_security import verify_password

from spkrepo.ext import db
from spkrepo.models import Package, User
from spkrepo.tests.common import BaseTestCase, BuildFactory, PackageFactory


def _invoke(test, *args):
    return test.app.test_cli_runner().invoke(args=["spkrepo", *args])


def _package_count():
    return db.session.scalar(db.select(db.func.count()).select_from(Package))


class CreateUserTestCase(BaseTestCase):
    def test_creates_active_user(self):
        result = _invoke(
            self, "create_user", "-u", "alice", "-e", "alice@example.com", "-p", "pw"
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("User Created", result.output)
        user = (
            db.session.execute(db.select(User).filter_by(username="alice"))
            .unique()
            .scalars()
            .one()
        )
        self.assertTrue(user.active)
        self.assertIsNotNone(user.confirmed_at)
        self.assertTrue(verify_password("pw", user.password))
        self.assertEqual(user.email, "alice@example.com")


class CreateAdminTestCase(BaseTestCase):
    ARGS = ("create_admin", "-u", "root", "-e", "root@example.com", "-p", "pw")

    def test_assigns_all_roles(self):
        result = _invoke(self, *self.ARGS)
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("Admin user created", result.output)
        user = (
            db.session.execute(db.select(User).filter_by(email="root@example.com"))
            .unique()
            .scalars()
            .one()
        )
        self.assertEqual(
            {role.name for role in user.roles},
            {"admin", "package_admin", "developer"},
        )

    def test_idempotent_by_email(self):
        self.assertEqual(_invoke(self, *self.ARGS).exit_code, 0)
        second = _invoke(self, *self.ARGS)
        self.assertEqual(second.exit_code, 0)
        self.assertIn("already exists", second.output)
        users = db.session.scalar(db.select(db.func.count()).select_from(User))
        self.assertEqual(users, 1)


class DestructiveCommandsTestCase(BaseTestCase):
    def _remote_build(self):
        package = PackageFactory()
        BuildFactory(version__package=package, storage="remote")
        db.session.commit()
        return package

    def test_depopulate_db_refuses_with_remote_build(self):
        package = self._remote_build()
        result = _invoke(self, "depopulate_db")
        self.assertIn("Refusing", result.output)
        self.assertEqual(_package_count(), 1)
        self.assertIsNotNone(Package.find(package.name))

    def test_clean_refuses_with_remote_build(self):
        self._remote_build()
        result = _invoke(self, "clean")
        self.assertIn("Refusing", result.output)

    def test_depopulate_db_deletes_local_packages(self):
        package = PackageFactory()
        BuildFactory(version__package=package, storage="local")
        db.session.commit()
        package_dir = os.path.join(self.app.config["DATA_PATH"], package.name)
        self.assertTrue(os.path.isdir(package_dir))

        result = _invoke(self, "depopulate_db")

        self.assertIn("Done", result.output)
        self.assertEqual(_package_count(), 0)
        self.assertFalse(os.path.exists(package_dir))

    def test_clean_removes_data_files(self):
        temp_data = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_data, ignore_errors=True)
        self.app.config["DATA_PATH"] = temp_data
        junk = os.path.join(temp_data, "sub", "junk.txt")
        os.makedirs(os.path.dirname(junk))
        with open(junk, "w", encoding="utf-8") as f:
            f.write("x")

        result = _invoke(self, "clean")

        self.assertIn("Done", result.output)
        self.assertFalse(os.path.exists(junk))
        self.assertFalse(os.path.exists(os.path.dirname(junk)))
