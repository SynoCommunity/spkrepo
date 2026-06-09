# -*- coding: utf-8 -*-
import hashlib
import io
import os
import shutil
from datetime import datetime, timezone

from flask import current_app
from flask_security import RoleMixin, SQLAlchemyUserDatastore, UserMixin
from sqlalchemy import event, select
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import Session
from sqlalchemy.orm.collections import attribute_mapped_collection
from sqlalchemy.sql.expression import FunctionElement

from .ext import db

user_role = db.Table(
    "user_role",
    db.Column("user_id", db.Integer(), db.ForeignKey("user.id"), index=True),
    db.Column("role_id", db.Integer(), db.ForeignKey("role.id"), index=True),
)

package_user_maintainer = db.Table(
    "package_user_maintainer",
    db.Column("package_id", db.Integer(), db.ForeignKey("package.id"), index=True),
    db.Column("user_id", db.Integer(), db.ForeignKey("user.id"), index=True),
)


class _days_ago(FunctionElement):
    """Dialect-aware SQL expression for a date N days in the past."""

    inherit_cache = True

    def __init__(self, days):
        self.days = days
        super().__init__()


@compiles(_days_ago, "sqlite")
def _compile_days_ago_sqlite(element, compiler, **kw):
    return f"date('now', '-{element.days} days')"


@compiles(_days_ago, "postgresql")
def _compile_days_ago_postgresql(element, compiler, **kw):
    return f"CURRENT_DATE - INTERVAL '{element.days} days'"


@compiles(_days_ago)
def _compile_days_ago_default(element, compiler, **kw):
    return f"date('now', '-{element.days} days')"


# Architecture code mappings — module-level constants, not instance data
_ARCH_FROM_SYNO = {"88f6281": "88f628x", "88f6282": "88f628x"}
_ARCH_TO_SYNO = {"88f628x": "88f6281"}


def _utcnow():
    """Return the current UTC time. Used as a per-insert Python-side default."""
    return datetime.now(timezone.utc)


class User(db.Model, UserMixin):
    __tablename__ = "user"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.Unicode(50), unique=True, nullable=False)
    email = db.Column(db.Unicode(254), unique=True, nullable=False)
    password = db.Column(db.Unicode(255), nullable=False)
    api_key = db.Column(db.Unicode(64), unique=True)
    github_access_token = db.Column(db.Unicode(255))
    fs_uniquifier = db.Column(db.String(255), unique=True, nullable=False)
    active = db.Column(db.Boolean(), nullable=False)
    confirmed_at = db.Column(db.DateTime())

    # Relationships
    roles = db.relationship(
        "Role", secondary="user_role", back_populates="users", lazy=False
    )
    authored_packages = db.relationship("Package", back_populates="author")
    maintained_packages = db.relationship(
        "Package", secondary="package_user_maintainer", back_populates="maintainers"
    )

    def __str__(self):
        return self.username

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.username}>"


class Role(db.Model, RoleMixin):
    __tablename__ = "role"

    # Columns
    id = db.Column(db.Integer(), primary_key=True)
    name = db.Column(db.Unicode(50), unique=True, nullable=False)
    description = db.Column(db.Unicode(255))

    # Relationships
    users = db.relationship("User", secondary="user_role", back_populates="roles")

    @classmethod
    def find(cls, name):
        return (
            db.session.execute(select(cls).filter(cls.name == name)).scalars().first()
        )

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name}>"


user_datastore = SQLAlchemyUserDatastore(db, User, Role)


class Architecture(db.Model):
    __tablename__ = "architecture"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.Unicode(20), unique=True, nullable=False)

    # Relationships
    builds = db.relationship(
        "Build", secondary="build_architecture", back_populates="architectures"
    )

    # Architecture code translation maps (references module-level constants)
    from_syno = _ARCH_FROM_SYNO
    to_syno = _ARCH_TO_SYNO

    @classmethod
    def find(cls, code, syno=False):
        if syno:
            code = _ARCH_FROM_SYNO.get(code, code)
        return (
            db.session.execute(select(cls).filter(cls.code == code)).scalars().first()
        )

    def __str__(self):
        return self.code

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.code}>"


class Language(db.Model):
    __tablename__ = "language"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.Unicode(3), unique=True, nullable=False)
    name = db.Column(db.Unicode(50))

    @classmethod
    def find(cls, code):
        return (
            db.session.execute(select(cls).filter(cls.code == code)).scalars().first()
        )

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__} [{self.code}] {self.name}>"


class Firmware(db.Model):
    __tablename__ = "firmware"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    version = db.Column(db.Unicode(4), nullable=False)
    build = db.Column(db.Integer, unique=True, nullable=False)
    type = db.Column(db.Unicode(4), nullable=False)

    @classmethod
    def find(cls, build):
        return (
            db.session.execute(select(cls).filter(cls.build == build)).scalars().first()
        )

    @property
    def firmware_string(self):
        return f"{self.version}-{self.build}"

    def __str__(self):
        return self.firmware_string

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.firmware_string}>"


class Screenshot(db.Model):
    __tablename__ = "screenshot"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer, db.ForeignKey("package.id"), nullable=False, index=True
    )
    path = db.Column(db.Unicode(200), nullable=False)

    # Relationships
    package = db.relationship("Package", back_populates="screenshots")

    def save(self, stream):
        with io.open(
            os.path.join(current_app.config["DATA_PATH"], self.path), "wb"
        ) as f:
            f.write(stream.read())

    def _after_insert(self):
        path = os.path.join(current_app.config["DATA_PATH"], self.path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Expected file not found after insert: {path}")

    def _after_delete(self):
        path = os.path.join(current_app.config["DATA_PATH"], self.path)
        if os.path.exists(path):
            os.remove(path)

    def __str__(self):
        return self.path

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.path}>"


class Icon(db.Model):
    __tablename__ = "icon"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"), nullable=False)
    size = db.Column(db.Enum("72", "120", "256", name="icon_size"), nullable=False)
    path = db.Column(db.Unicode(100), nullable=False)

    # Constraints
    __table_args__ = (db.UniqueConstraint(version_id, size),)

    # Relationships
    version = db.relationship("Version", back_populates="icons")

    def save(self, stream):
        with io.open(
            os.path.join(current_app.config["DATA_PATH"], self.path), "wb"
        ) as f:
            f.write(stream.read())

    def _after_insert(self):
        path = os.path.join(current_app.config["DATA_PATH"], self.path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Expected file not found after insert: {path}")

    def _after_delete(self):
        path = os.path.join(current_app.config["DATA_PATH"], self.path)
        if os.path.exists(path):
            os.remove(path)

    def __str__(self):
        return self.path

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.path}>"


class Service(db.Model):
    __tablename__ = "service"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.Unicode(30), unique=True, nullable=False)

    @classmethod
    def find(cls, code):
        return (
            db.session.execute(select(cls).filter(cls.code == code)).scalars().first()
        )

    def __str__(self):
        return self.code

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.code}>"


class DisplayName(db.Model):
    __tablename__ = "displayname"

    # Columns
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"), nullable=False)
    language_id = db.Column(db.Integer, db.ForeignKey("language.id"), nullable=False)
    displayname = db.Column(db.Unicode(50), nullable=False)

    # Relationships
    language = db.relationship("Language")

    # Constraints
    __table_args__ = (db.PrimaryKeyConstraint(version_id, language_id),)

    def __str__(self):
        return self.displayname

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.language.name}>"


class BuildDescription(db.Model):
    __tablename__ = "build_description"

    # Columns
    build_id = db.Column(db.Integer, db.ForeignKey("build.id"), nullable=False)
    language_id = db.Column(db.Integer, db.ForeignKey("language.id"), nullable=False)
    description = db.Column(db.UnicodeText, nullable=False)

    # Relationships
    language = db.relationship("Language")

    # Constraints
    __table_args__ = (db.PrimaryKeyConstraint(build_id, language_id),)

    def __str__(self):
        return self.description

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.language.name}>"


version_service_dependency = db.Table(
    "version_service_dependency",
    db.Column("version_id", db.Integer(), db.ForeignKey("version.id"), index=True),
    db.Column("service_id", db.Integer(), db.ForeignKey("service.id"), index=True),
)


class DownloadStat(db.Model):
    __tablename__ = "download_stat"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer, db.ForeignKey("package.id"), nullable=False, index=True
    )
    build_id = db.Column(
        db.Integer,
        db.ForeignKey("build.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    architecture_id = db.Column(
        db.Integer, db.ForeignKey("architecture.id"), nullable=False, index=True
    )
    firmware_build = db.Column(db.Integer, nullable=False, index=True)
    date = db.Column(db.Date, nullable=False, index=True)
    count = db.Column(db.Integer, nullable=False, default=0)

    # Constraints
    __table_args__ = (
        db.UniqueConstraint(
            "package_id",
            "architecture_id",
            "firmware_build",
            "date",
            name="uq_download_stat",
        ),
        db.Index("ix_download_stat_package_id_date", "package_id", "date"),
    )

    # Relationships
    package = db.relationship("Package", back_populates="download_stats")
    build = db.relationship("Build", back_populates="download_stats")
    architecture = db.relationship("Architecture")

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} package={self.package_id} "
            f"date={self.date} count={self.count}>"
        )


build_architecture = db.Table(
    "build_architecture",
    db.Column("build_id", db.Integer(), db.ForeignKey("build.id"), index=True),
    db.Column(
        "architecture_id", db.Integer(), db.ForeignKey("architecture.id"), index=True
    ),
)


class Build(db.Model):
    __tablename__ = "build"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"), nullable=False)
    firmware_min_id = db.Column(
        db.Integer, db.ForeignKey("firmware.id"), nullable=False, index=True
    )
    firmware_max_id = db.Column(db.Integer, db.ForeignKey("firmware.id"), index=True)
    publisher_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True)
    checksum = db.Column(db.Unicode(32))
    changelog = db.Column(db.UnicodeText)
    path = db.Column(db.Unicode(2048))
    md5 = db.Column(db.Unicode(32))
    size = db.Column(db.Integer)
    insert_date = db.Column(db.DateTime, default=_utcnow, nullable=False)
    active = db.Column(db.Boolean(), default=False, nullable=False)

    # Constraints
    __table_args__ = (db.Index("idx_build_version_active", "version_id", "active"),)

    # Relationships
    version = db.relationship("Version", back_populates="builds", lazy=False)
    architectures = db.relationship(
        "Architecture",
        secondary="build_architecture",
        order_by="Architecture.code",
        lazy=False,
    )
    firmware_min = db.relationship(
        "Firmware",
        foreign_keys=[firmware_min_id],
        lazy=False,
    )
    firmware_max = db.relationship(
        "Firmware",
        foreign_keys=[firmware_max_id],
        lazy=False,
    )
    publisher = db.relationship("User", foreign_keys=[publisher_user_id])
    download_stats = db.relationship(
        "DownloadStat",
        back_populates="build",
        cascade="save-update, merge",
        passive_deletes=True,
    )
    buildmanifest = db.relationship(
        "BuildManifest",
        back_populates="build",
        cascade="all, delete-orphan",
        uselist=False,
    )
    descriptions = db.relationship(
        "BuildDescription",
        cascade="all, delete-orphan",
        collection_class=attribute_mapped_collection("language.code"),
    )

    @classmethod
    def generate_filename(cls, package, version, firmware, architectures):
        """
        Backward-compatible signature.
        Pass the intended firmware (typically firmware_min) from the caller.
        """
        arch_codes = "-".join(a.code for a in architectures)
        return f"{package.name}.v{version.version}.f{firmware.build}[{arch_codes}].spk"

    def save(self, stream):
        with io.open(
            os.path.join(current_app.config["DATA_PATH"], self.path), "wb"
        ) as f:
            f.write(stream.read())

    def calculate_md5(self):
        if not self.path:
            raise ValueError("Path cannot be empty.")
        file_path = os.path.join(current_app.config["DATA_PATH"], self.path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at path: {file_path}")
        with io.open(file_path, "rb") as f:
            md5_hash = hashlib.md5()
            for chunk in iter(lambda: f.read(4096), b""):
                md5_hash.update(chunk)
            return md5_hash.hexdigest()

    def calculate_size(self):
        if not self.path:
            raise ValueError("Path cannot be empty.")
        file_path = os.path.join(current_app.config["DATA_PATH"], self.path)
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found at path: {file_path}")
        return os.path.getsize(file_path)

    def _before_insert(self):
        self._insert_path = os.path.join(current_app.config["DATA_PATH"], self.path)

    def _after_insert(self):
        if not os.path.exists(self._insert_path):
            raise FileNotFoundError(
                f"Expected file not found after insert: {self._insert_path}"
            )

    def _before_delete(self):
        self._delete_path = os.path.join(current_app.config["DATA_PATH"], self.path)

    def _after_delete(self):
        if os.path.exists(self._delete_path):
            os.remove(self._delete_path)

    def __str__(self):
        return self.path

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.path}>"


class BuildManifest(db.Model):
    __tablename__ = "buildmanifest"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    build_id = db.Column(
        db.Integer, db.ForeignKey("build.id"), nullable=False, unique=True
    )
    dependencies = db.Column(db.Unicode(255))
    conf_dependencies = db.Column(db.UnicodeText)
    conflicts = db.Column(db.Unicode(255))
    conf_conflicts = db.Column(db.UnicodeText)
    conf_privilege = db.Column(db.UnicodeText)
    conf_resource = db.Column(db.UnicodeText)

    # Relationships
    build = db.relationship("Build", back_populates="buildmanifest")

    def __repr__(self):
        return f"<{self.__class__.__name__} build_id={self.build_id}>"


class Version(db.Model):
    __tablename__ = "version"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    package_id = db.Column(
        db.Integer, db.ForeignKey("package.id"), nullable=False, index=True
    )
    version = db.Column(db.Integer, nullable=False, index=True)
    upstream_version = db.Column(db.Unicode(20), nullable=False)
    report_url = db.Column(db.Unicode(255))
    distributor = db.Column(db.Unicode(50))
    distributor_url = db.Column(db.Unicode(255))
    maintainer = db.Column(db.Unicode(50))
    maintainer_url = db.Column(db.Unicode(255))
    install_wizard = db.Column(db.Boolean)
    upgrade_wizard = db.Column(db.Boolean)
    startable = db.Column(db.Boolean)
    license = db.Column(db.UnicodeText)
    insert_date = db.Column(db.DateTime, default=_utcnow, nullable=False)

    # Relationships
    package = db.relationship("Package", back_populates="versions", lazy=False)
    service_dependencies = db.relationship(
        "Service", secondary="version_service_dependency"
    )
    displaynames = db.relationship(
        "DisplayName",
        cascade="all, delete-orphan",
        collection_class=attribute_mapped_collection("language.code"),
    )
    icons = db.relationship(
        "Icon",
        back_populates="version",
        cascade="all, delete-orphan",
        collection_class=attribute_mapped_collection("size"),
    )
    builds = db.relationship(
        "Build",
        back_populates="version",
        cascade="all, delete-orphan",
        cascade_backrefs=False,
    )

    # Constraints
    __table_args__ = (db.UniqueConstraint(package_id, version),)

    @hybrid_property
    def beta(self):
        return bool(self.report_url)  # Treats None and "" as False

    @beta.expression
    def beta(cls):
        return db.and_(cls.report_url.isnot(None), cls.report_url != "")

    @hybrid_property
    def all_builds_active(self):
        return all(b.active for b in self.builds)

    @all_builds_active.expression
    def all_builds_active(cls):
        return ~db.exists().where(
            db.and_(Build.version_id == cls.id, Build.active.is_(False))
        )

    @property
    def path(self):
        return os.path.join(self.package.name, str(self.version))

    @property
    def version_string(self):
        return self.upstream_version + "-" + str(self.version)

    def _before_insert(self):
        self._insert_path = os.path.join(current_app.config["DATA_PATH"], self.path)

    def _after_insert(self):
        if not os.path.exists(self._insert_path):
            raise FileNotFoundError(
                f"Expected file not found after insert: {self._insert_path}"
            )

    def _before_delete(self):
        self._delete_path = os.path.join(current_app.config["DATA_PATH"], self.path)

    def _after_delete(self):
        if os.path.exists(self._delete_path):
            shutil.rmtree(self._delete_path)

    def __str__(self):
        return self.version_string

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.version_string}>"

    @property
    def builds_per_dsm(self):
        result = {}
        for build in self.builds:
            result.setdefault(build.firmware_min.version.split(".")[0], []).append(
                build
            )
        return result

    @hybrid_property
    def total_size(self):
        # Returns None if no builds have a known size, rather than 0
        total = sum(b.size for b in self.builds if b.size is not None)
        return total or None

    @total_size.expression
    def total_size(cls):
        return (
            db.select(db.func.sum(Build.size))
            .where(Build.version_id == cls.id)
            .correlate(cls)
            .scalar_subquery()
        )


Version.download_count = db.column_property(
    db.select(db.func.coalesce(db.func.sum(DownloadStat.count), 0))
    .join(Build, Build.id == DownloadStat.build_id)
    .where(Build.version_id == Version.id)
    .correlate(Version)
    .scalar_subquery(),
    deferred=True,
)

Version.recent_download_count = db.column_property(
    db.select(db.func.coalesce(db.func.sum(DownloadStat.count), 0))
    .join(Build, Build.id == DownloadStat.build_id)
    .where(
        db.and_(
            Build.version_id == Version.id,
            DownloadStat.date >= _days_ago(90),
        )
    )
    .correlate(Version)
    .scalar_subquery(),
    deferred=True,
)


class Package(db.Model):
    __tablename__ = "package"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    author_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL"), index=True
    )
    name = db.Column(db.Unicode(50), nullable=False)
    insert_date = db.Column(db.DateTime, default=_utcnow, nullable=False)
    download_count = db.column_property(
        db.select(db.func.coalesce(db.func.sum(DownloadStat.count), 0))
        .where(DownloadStat.package_id == id)
        .scalar_subquery(),
        deferred=True,
    )
    recent_download_count = db.column_property(
        db.select(db.func.coalesce(db.func.sum(DownloadStat.count), 0))
        .where(
            db.and_(
                DownloadStat.package_id == id,
                DownloadStat.date >= _days_ago(90),
            )
        )
        .scalar_subquery(),
        deferred=True,
    )
    last_download_date = db.column_property(
        db.select(db.func.max(DownloadStat.date))
        .where(DownloadStat.package_id == id)
        .scalar_subquery(),
        deferred=True,
    )

    # Relationships
    versions = db.relationship(
        "Version",
        back_populates="package",
        cascade="all, delete-orphan",
        cascade_backrefs=False,
        order_by="Version.version",
    )
    screenshots = db.relationship(
        "Screenshot", back_populates="package", cascade="all, delete-orphan"
    )
    author = db.relationship("User", back_populates="authored_packages")
    maintainers = db.relationship(
        "User",
        secondary="package_user_maintainer",
        back_populates="maintained_packages",
    )
    download_stats = db.relationship(
        "DownloadStat",
        back_populates="package",
        cascade="all, delete-orphan",
    )

    # Constraints
    __table_args__ = (db.UniqueConstraint(name),)

    @classmethod
    def find(cls, name):
        return (
            db.session.execute(select(cls).filter(cls.name == name)).scalars().first()
        )

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name}>"


def _before_insert_handler(mapper, connection, target):
    if hasattr(target, "_before_insert"):
        target._before_insert()


def _after_insert_handler(mapper, connection, target):
    if not hasattr(target, "_after_insert"):
        return
    session = Session.object_session(target)
    if session is None:
        return

    @event.listens_for(session, "after_commit", once=True)
    def on_commit(session):
        target._after_insert()


def _before_delete_handler(mapper, connection, target):
    if hasattr(target, "_before_delete"):
        target._before_delete()


def _after_delete_handler(mapper, connection, target):
    if not hasattr(target, "_after_delete"):
        return
    session = Session.object_session(target)
    if session is None:
        return

    @event.listens_for(session, "after_commit", once=True)
    def on_commit(session):
        target._after_delete()


for _model in [Screenshot, Icon, Build, Version]:
    event.listen(_model, "before_insert", _before_insert_handler)
    event.listen(_model, "after_insert", _after_insert_handler)
    event.listen(_model, "before_delete", _before_delete_handler)
    event.listen(_model, "after_delete", _after_delete_handler)
