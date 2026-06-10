import os
import shutil

import click
from flask import current_app
from flask.cli import with_appcontext

from .ext import db
from .models import Build, Package, Role, User


def _create_user(username, email, password):
    from spkrepo.tests.common import UserFactory

    with db.session.no_autoflush:
        UserFactory(username=username, email=email, password=password)
    db.session.commit()


@click.group()
def spkrepo():
    """Spkrepo admin commands."""


@spkrepo.command("create_user")
@click.option("-u", "--username", prompt=True, help="username")
@click.option("-e", "--email", prompt=True, help="email")
@click.option("-p", "--password", prompt=True, hide_input=True, help="password")
@with_appcontext
def create_user(username, email, password):
    """Create a new user with an activated account."""
    _create_user(username, email, password)
    click.echo("User Created")


@spkrepo.command("populate_db")
@with_appcontext
def populate_db():
    """Populate the database with some sample packages."""

    from spkrepo.models import Architecture, BuildManifest
    from spkrepo.tests.common import BuildFactory, PackageFactory, VersionFactory

    def attach_manifest(build, *, dependencies=None):
        """Attach a simple manifest to a build with optional dependencies."""
        manifest = BuildManifest(
            dependencies=dependencies,
            conf_dependencies=None,
            conflicts=None,
            conf_conflicts=None,
            conf_privilege=None,
            conf_resource=None,
        )
        build.buildmanifest = manifest

    with db.session.no_autoflush:
        # nzbget
        nzbget_package = PackageFactory(name="nzbget")
        nzbget_versions = [
            VersionFactory(
                package=nzbget_package,
                upstream_version="12.0",
                version=10,
                report_url=None,
                install_wizard=True,
                upgrade_wizard=False,
            ),
            VersionFactory(
                package=nzbget_package,
                upstream_version="13.0",
                version=11,
                report_url=None,
                install_wizard=True,
                upgrade_wizard=False,
            ),
        ]
        nzbget_builds = []
        for version in nzbget_versions:
            builds = BuildFactory.create_batch(
                2, version=version, active=True, buildmanifest=False
            )
            nzbget_builds.extend(builds)

        # sickbeard
        sickbeard_package = PackageFactory(name="sickbeard")
        sickbeard_versions = [
            VersionFactory(
                package=sickbeard_package,
                upstream_version="20140528",
                version=3,
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
            VersionFactory(
                package=sickbeard_package,
                upstream_version="20140702",
                version=4,
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
                    buildmanifest=False,
                )
            )
            attach_manifest(sickbeard_builds[-1], dependencies="git")

        # git
        git_package = PackageFactory(name="git")
        git_versions = [
            VersionFactory(
                package=git_package,
                upstream_version="1.8.4",
                version=3,
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=False,
            ),
            VersionFactory(
                package=git_package,
                upstream_version="2.1.2",
                version=4,
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=False,
            ),
        ]
        git_builds = []
        for version in git_versions:
            builds = BuildFactory.create_batch(
                3, version=version, active=True, buildmanifest=False
            )
            git_builds.extend(builds)

        # bitlbee
        bitlbee_package = PackageFactory(name="bitlbee")
        bitlbee_versions = [
            VersionFactory(
                package=bitlbee_package,
                upstream_version="3.2.2",
                version=9,
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
            VersionFactory(
                package=bitlbee_package,
                upstream_version="3.2.3",
                version=10,
                report_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
            VersionFactory(
                package=bitlbee_package,
                upstream_version="3.3.0",
                version=11,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
            ),
        ]
        bitlbee_builds = []
        for version in bitlbee_versions:
            builds = BuildFactory.create_batch(
                3, version=version, active=True, buildmanifest=False
            )
            bitlbee_builds.extend(builds)
    db.session.commit()


@spkrepo.command("depopulate_db")
@with_appcontext
def depopulate_db():
    """Delete all packages from database and file system."""
    if db.session.query(Build).filter(Build.storage != "local").first():
        click.echo("Refusing: builds exist in Object Storage. Run only on local-only databases.")
        return
    for package in Package.query.all():
        db.session.delete(package)
        shutil.rmtree(
            os.path.join(current_app.config["DATA_PATH"], package.name),
            ignore_errors=True,
        )

    db.session.commit()
    click.echo("Done")


@spkrepo.command("create_admin")
@click.option("-u", "--username", default="admin", help="username")
@click.option("-e", "--email", default="admin@synocommunity.com", help="email")
@click.option("-p", "--password", prompt=True, hide_input=True, help="password")
@with_appcontext
def create_admin(username, email, password):
    """Create a new super admin user."""
    click.echo("Creating admin user…")
    existing_admin = User.query.filter_by(email=email).first()
    if existing_admin:
        click.echo(f"'{username}' user already exists, skipping creation")
    else:
        _create_user(
            username=username,
            email=email,
            password=password,
        )

    user = User.query.filter_by(email=email).first()
    if not user:
        raise ValueError(f"No user with email {email}")

    for role_name in ("admin", "package_admin", "developer"):
        role = Role.query.filter_by(name=role_name).first()
        if not role:
            raise ValueError(f"No role with name '{role_name}'")

        if role not in user.roles:
            user.roles.append(role)
            db.session.commit()
            click.echo(f"'{username}' user assigned '{role}' role")

    click.echo("Admin user created")


@spkrepo.command("clean")
@with_appcontext
def clean():
    """Clean data path, removes all packages on filesystem."""
    if db.session.query(Build).filter(Build.storage != "local").first():
        click.echo("Refusing: builds exist in Object Storage. Run only on local-only databases.")
        return
    # do not remove and recreate the path since it may be a docker volume
    for root, dirs, files in os.walk(
        os.path.join(current_app.config["DATA_PATH"]), topdown=False
    ):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    click.echo("Done")



@spkrepo.command("ingest_logs")
@with_appcontext
def ingest_logs():
    """Ingest download stats from Object Storage log files."""
    import gzip
    import json
    import logging
    import re
    from collections import defaultdict
    from datetime import date, datetime

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError
    from sqlalchemy.dialects.postgresql import insert as pg_insert

    from .models import Architecture, Build, DownloadStat, Version

    logger = logging.getLogger(__name__)

    def is_countable_download(record):
        url = record.get("url", "")
        path = url.split("?")[0]
        if not path.endswith(".spk"):
            return False
        status = record.get("response_status")
        if status == 200:
            return True
        if status == 206:
            range_header = record.get("range", "")
            return range_header == "" or range_header.startswith("bytes=0-")
        return False

    def parse_download(record):
        url = record.get("url", "")
        path = url.split("?")[0]
        match = re.match(r"^/([^/]+)/([^/]+)/", path)
        if not match:
            return None
        package_name = match.group(1)
        try:
            version_number = int(match.group(2))
        except ValueError:
            return None
        arch_code = record.get("arch") or None
        firmware_build = record.get("build") or None
        if firmware_build is not None:
            try:
                firmware_build = int(firmware_build)
            except ValueError:
                firmware_build = None
        try:
            record_date = datetime.fromisoformat(record["timestamp"]).date()
        except (KeyError, ValueError):
            record_date = date.today()
        return package_name, version_number, arch_code, firmware_build, record_date

    bucket = current_app.config["OBJECT_STORAGE_LOGS_BUCKET"]
    prefix = current_app.config.get("OBJECT_STORAGE_LOGS_PREFIX", "logs/")

    s3 = boto3.client(
        "s3",
        endpoint_url=current_app.config["OBJECT_STORAGE_LOGS_ENDPOINT"],
        aws_access_key_id=current_app.config["OBJECT_STORAGE_LOGS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["OBJECT_STORAGE_LOGS_SECRET_KEY"],
        region_name=current_app.config.get("OBJECT_STORAGE_LOGS_REGION", "us-east"),
    )

    try:
        response = s3.list_objects_v2(Bucket=bucket, Prefix=prefix)
    except (BotoCoreError, ClientError) as e:
        logger.error("Failed to list objects in bucket: %s", e)
        return

    objects = response.get("Contents", [])
    if not objects:
        logger.info("No log files to process.")
        return

    logger.info("Processing %d log file(s).", len(objects))

    build_cache = {}  # (package_name, version_number) -> (build_id, package_id) or None
    arch_cache = {}  # arch_code -> architecture_id or None
    counts = defaultdict(int)
    build_ids = {}  # agg_key -> build_id or None
    processed_keys = []

    skipped_no_arch = 0
    skipped_no_build = 0
    skipped_no_arch_id = 0

    for obj in objects:
        key = obj["Key"]
        try:
            body = s3.get_object(Bucket=bucket, Key=key)["Body"]
            lines = gzip.open(body, "rt") if key.endswith(".gz") else body.iter_lines()

            for raw_line in lines:
                if isinstance(raw_line, bytes):
                    raw_line = raw_line.decode("utf-8")
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    record = json.loads(raw_line)
                except json.JSONDecodeError:
                    continue
                if not is_countable_download(record):
                    continue
                parsed = parse_download(record)
                if parsed is None:
                    continue
                package_name, version_number, arch_code, firmware_build, record_date = (
                    parsed
                )

                if arch_code is None or firmware_build is None:
                    skipped_no_arch += 1
                    continue

                cache_key = (package_name, version_number)
                if cache_key not in build_cache:
                    build = (
                        db.session.query(Build)
                        .join(Version)
                        .filter(
                            Version.version == version_number,
                            Version.package.has(name=package_name),
                        )
                        .first()
                    )
                    if build:
                        build_cache[cache_key] = (build.id, build.version.package_id)
                    else:
                        build_cache[cache_key] = None

                cached = build_cache[cache_key]
                if cached is None:
                    skipped_no_build += 1
                    continue
                build_id, package_id = cached

                if arch_code not in arch_cache:
                    arch = Architecture.find(arch_code, syno=True)
                    arch_cache[arch_code] = arch.id if arch else None
                architecture_id = arch_cache[arch_code]

                if architecture_id is None:
                    skipped_no_arch_id += 1
                    continue

                agg_key = (package_id, architecture_id, firmware_build, record_date)
                counts[agg_key] += 1

                if agg_key not in build_ids:
                    build_ids[agg_key] = build_id
                elif build_ids[agg_key] != build_id:
                    build_ids[agg_key] = None

            processed_keys.append(key)

        except (BotoCoreError, ClientError) as e:
            logger.error("Failed to read %s: %s", key, e)
            continue

    if counts:
        rows = [
            {
                "package_id": package_id,
                "build_id": build_ids.get(agg_key),
                "architecture_id": architecture_id,
                "firmware_build": firmware_build,
                "date": record_date,
                "count": count,
            }
            for agg_key, count in counts.items()
            for (package_id, architecture_id, firmware_build, record_date) in [agg_key]
        ]
        try:
            stmt = pg_insert(DownloadStat).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_download_stat",
                set_={"count": DownloadStat.count + stmt.excluded.count},
            )
            db.session.execute(stmt)
            db.session.commit()
        except Exception as e:
            logger.error("Failed to upsert download stats: %s", e)
            return

    for key in processed_keys:
        try:
            s3.delete_object(Bucket=bucket, Key=key)
        except (BotoCoreError, ClientError) as e:
            logger.warning("Failed to delete %s: %s", key, e)

    logger.info(
        "Ingested %d download events from %d file(s). "
        "Skipped — missing arch/firmware: %d, "
        "unknown package/version: %d, unknown architecture: %d.",
        sum(counts.values()),
        len(processed_keys),
        skipped_no_arch,
        skipped_no_build,
        skipped_no_arch_id,
    )
