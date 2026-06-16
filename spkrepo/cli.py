import logging
import os
import shutil
import urllib.parse

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
        click.echo("Refusing: builds in Object Storage. Use local-only DB.")
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
        click.echo("Refusing: builds in Object Storage. Use local-only DB.")
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
    import re
    from collections import defaultdict
    from datetime import date, datetime

    import boto3
    from botocore.exceptions import BotoCoreError, ClientError

    from .models import Architecture, Build, DownloadStat

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
        path = urllib.parse.unquote(url.split("?")[0])
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

        # Parse target info from the SPK filename
        target_firmware_build = None
        target_noarch = False
        filename = path.rsplit("/", 1)[-1] if "/" in path else path
        fm = re.search(r"\.f(\d+)\[([^\]]+)\]", filename)
        if fm:
            archs = fm.group(2).split("-")
            target_noarch = "noarch" in archs
            if not target_noarch:
                target_firmware_build = int(fm.group(1))

        return (
            path.lstrip("/"),
            arch_code,
            firmware_build,
            record_date,
            target_firmware_build,
            target_noarch,
        )

    bucket = current_app.config["OBJECT_STORAGE_LOGS_BUCKET"]
    prefix = current_app.config.get("OBJECT_STORAGE_LOGS_PREFIX", "logs/")

    s3 = boto3.client(
        "s3",
        endpoint_url=current_app.config["OBJECT_STORAGE_LOGS_ENDPOINT"],
        aws_access_key_id=current_app.config["OBJECT_STORAGE_LOGS_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["OBJECT_STORAGE_LOGS_SECRET_KEY"],
        region_name=current_app.config["OBJECT_STORAGE_LOGS_REGION"],
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

    # url_path -> (build_id, pkg_id) or None
    build_cache = {}
    arch_cache = {}  # arch_code -> architecture_id or None
    counts = defaultdict(int)
    build_ids = {}  # agg_key -> build_id or None
    target_noarchs = {}  # agg_key -> bool
    processed_keys = []

    skipped_no_arch = 0
    skipped_no_build = 0

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
                (
                    url_path,
                    arch_code,
                    firmware_build,
                    record_date,
                    target_firmware_build,
                    target_noarch,
                ) = parsed

                if arch_code is None or firmware_build is None:
                    skipped_no_arch += 1
                    continue

                if url_path not in build_cache:
                    build = (
                        db.session.query(Build).filter(Build.path == url_path).first()
                    )
                    if build:
                        build_cache[url_path] = (build.id, build.version.package_id)
                    else:
                        build_cache[url_path] = None

                cached = build_cache[url_path]
                if cached is None:
                    skipped_no_build += 1
                    continue
                build_id, package_id = cached

                if arch_code not in arch_cache:
                    arch = Architecture.find(arch_code, syno=True)
                    arch_cache[arch_code] = arch.id
                architecture_id = arch_cache[arch_code]

                agg_key = (
                    package_id,
                    architecture_id,
                    firmware_build,
                    target_firmware_build,
                    record_date,
                )
                counts[agg_key] += 1
                target_noarchs[agg_key] = target_noarch

                if agg_key not in build_ids:
                    build_ids[agg_key] = build_id

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
                "target_firmware_build": target_firmware_build,
                "target_noarch": target_noarchs.get(agg_key, False),
                "date": record_date,
                "count": count,
            }
            for agg_key, count in counts.items()
            for (
                package_id,
                architecture_id,
                firmware_build,
                target_firmware_build,
                record_date,
            ) in [agg_key]
        ]
        try:
            dialect = db.engine.dialect.name
            if dialect == "postgresql":
                from sqlalchemy.dialects.postgresql import insert as upsert_insert
            elif dialect == "sqlite":
                from sqlalchemy.dialects.sqlite import insert as upsert_insert
            else:
                raise RuntimeError(f"Upsert not supported for dialect: {dialect}")

            stmt = upsert_insert(DownloadStat).values(rows)
            stmt = stmt.on_conflict_do_update(
                constraint="uq_download_stat",
                set_={
                    "count": DownloadStat.count + stmt.excluded.count,
                    "target_noarch": stmt.excluded.target_noarch,
                },
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
        "Skipped — missing arch/firmware: %d, unknown build path: %d.",
        sum(counts.values()),
        len(processed_keys),
        skipped_no_arch,
        skipped_no_build,
    )
