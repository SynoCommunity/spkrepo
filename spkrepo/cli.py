import os
import shutil

import click
from flask.cli import with_appcontext

from .ext import db


@click.group()
def spkrepo():
    """Spkrepo admin commands."""


@spkrepo.command("create_user")
@click.option("-u", "--username", help="username", default=None)
@click.option("-e", "--email", help="email", default=None)
@click.option("-p", "--password", help="password", default=None)
@with_appcontext
def create_user(username, email, password):
    """Create a new user with an activated account."""
    from spkrepo.tests.common import UserFactory

    with db.session.no_autoflush:
        UserFactory(username=username, email=email, password=password)
    db.session.commit()


@spkrepo.command("populate_db")
@with_appcontext
def populate_db():
    """Populate the database with some packages."""
    from spkrepo.models import Architecture
    from spkrepo.tests.common import BuildFactory, PackageFactory, VersionFactory

    with db.session.no_autoflush:
        # nzbget
        nzbget_package = PackageFactory(name="nzbget")
        nzbget_versions = [
            VersionFactory(
                package=nzbget_package,
                upstream_version="12.0",
                version=10,
                dependencies=None,
                report_url=None,
                install_wizard=True,
                upgrade_wizard=False,
            ),
            VersionFactory(
                package=nzbget_package,
                upstream_version="13.0",
                version=11,
                dependencies=None,
                report_url=None,
                install_wizard=True,
                upgrade_wizard=False,
            ),
        ]
        nzbget_builds = []
        for version in nzbget_versions:
            builds = BuildFactory.create_batch(2, version=version, active=True)
            nzbget_builds.extend(builds)

        # sickbeard
        sickbeard_package = PackageFactory(name="sickbeard")
        sickbeard_versions = [
            VersionFactory(
                package=sickbeard_package,
                upstream_version="20140528",
                version=3,
                dependencies="git",
                service_dependencies=[],
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
            VersionFactory(
                package=sickbeard_package,
                upstream_version="20140702",
                version=4,
                dependencies="git",
                service_dependencies=[],
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
        ]
        sickbeard_builds = []
        for version in sickbeard_versions:
            sickbeard_builds.append(
                BuildFactory(
                    version=version,
                    architectures=[Architecture.find("noarch")],
                    active=True,
                )
            )

        # git
        git_package = PackageFactory(name="git")
        git_versions = [
            VersionFactory(
                package=git_package,
                upstream_version="1.8.4",
                version=3,
                dependencies=None,
                service_dependencies=[],
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=False,
            ),
            VersionFactory(
                package=git_package,
                upstream_version="2.1.2",
                version=4,
                dependencies=None,
                service_dependencies=[],
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=False,
            ),
        ]
        git_builds = []
        for version in git_versions:
            builds = BuildFactory.create_batch(3, version=version, active=True)
            git_builds.extend(builds)

        # bitlbee
        bitlbee_package = PackageFactory(name="bitlbee")
        bitlbee_versions = [
            VersionFactory(
                package=bitlbee_package,
                upstream_version="3.2.2",
                version=9,
                dependencies=None,
                service_dependencies=[],
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
            VersionFactory(
                package=bitlbee_package,
                upstream_version="3.2.3",
                version=10,
                dependencies=None,
                service_dependencies=[],
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
            VersionFactory(
                package=bitlbee_package,
                upstream_version="3.3.0",
                version=11,
                dependencies=None,
                service_dependencies=[],
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
        ]
        bitlbee_builds = []
        for version in bitlbee_versions:
            builds = BuildFactory.create_batch(3, version=version, active=True)
            bitlbee_builds.extend(builds)
    db.session.commit()


@spkrepo.command("depopulate_db")
@with_appcontext
def depopulate_db():
    """Depopulate database."""
    from flask import current_app

    from spkrepo.models import Package

    for package in Package.query.all():
        # Delete the package and its associated versions and builds
        db.session.delete(package)

        # Remove the directory associated with the package (if it exists)
        shutil.rmtree(
            os.path.join(current_app.config["DATA_PATH"], package.name),
            ignore_errors=True,
        )

    db.session.commit()


@spkrepo.command("clean")
@with_appcontext
def clean():
    """Clean data path."""
    from flask import current_app

    # do not remove and recreate the path since it may be a docker volume
    for root, dirs, files in os.walk(
        os.path.join(current_app.config["DATA_PATH"]), topdown=False
    ):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
