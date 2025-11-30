# -*- coding: utf-8 -*-
import hashlib
import io
import os
import shutil
from datetime import datetime, timedelta

from flask import current_app
from flask_security import RoleMixin, SQLAlchemyUserDatastore, UserMixin
from flask_sqlalchemy import track_modifications
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm.collections import attribute_mapped_collection

from .ext import db

user_role = db.Table(
    "user_role",
    db.Column("user_id", db.Integer(), db.ForeignKey("user.id")),
    db.Column("role_id", db.Integer(), db.ForeignKey("role.id")),
)

package_user_maintainer = db.Table(
    "package_user_maintainer",
    db.Column("package_id", db.Integer(), db.ForeignKey("package.id")),
    db.Column("user_id", db.Integer(), db.ForeignKey("user.id")),
)


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
        return cls.query.filter(cls.name == name).first()

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

    # Other
    from_syno = {"88f6281": "88f628x", "88f6282": "88f628x"}
    to_syno = {"88f628x": "88f6281"}

    @classmethod
    def find(cls, code, syno=False):
        if syno:
            return cls.query.filter(cls.code == cls.from_syno.get(code, code)).first()
        return cls.query.filter(cls.code == code).first()

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
        return cls.query.filter(cls.code == code).first()

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
        return cls.query.filter(cls.build == build).first()

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
    package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=False)
    path = db.Column(db.Unicode(200), nullable=False)

    # Relationships
    package = db.relationship("Package", back_populates="screenshots")

    def save(self, stream):
        with io.open(
            os.path.join(current_app.config["DATA_PATH"], self.path), "wb"
        ) as f:
            f.write(stream.read())

    def _after_insert(self):
        assert os.path.exists(os.path.join(current_app.config["DATA_PATH"], self.path))

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
        assert os.path.exists(os.path.join(current_app.config["DATA_PATH"], self.path))

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
        return cls.query.filter(cls.code == code).first()

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


class Description(db.Model):
    __tablename__ = "description"

    # Columns
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"), nullable=False)
    language_id = db.Column(db.Integer, db.ForeignKey("language.id"), nullable=False)
    description = db.Column(db.UnicodeText, nullable=False)

    # Relationships
    language = db.relationship("Language")

    # Constraints
    __table_args__ = (db.PrimaryKeyConstraint(version_id, language_id),)

    def __str__(self):
        return self.description

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.language.name}>"


version_service_dependency = db.Table(
    "version_service_dependency",
    db.Column("version_id", db.Integer(), db.ForeignKey("version.id")),
    db.Column("service_id", db.Integer(), db.ForeignKey("service.id")),
)


class Download(db.Model):
    __tablename__ = "download"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    build_id = db.Column(db.Integer, db.ForeignKey("build.id"), nullable=False)
    architecture_id = db.Column(
        db.Integer, db.ForeignKey("architecture.id"), nullable=False
    )
    firmware_build = db.Column(db.Integer, nullable=False)
    ip_address = db.Column(db.Unicode(46), nullable=False)
    user_agent = db.Column(db.Unicode(255))
    date = db.Column(db.DateTime, default=db.func.now(), nullable=False)

    # Relationships
    build = db.relationship("Build", back_populates="downloads")
    architecture = db.relationship("Architecture")

    def __str__(self):
        return self.ip_address

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.ip_address}>"


build_architecture = db.Table(
    "build_architecture",
    db.Column("build_id", db.Integer(), db.ForeignKey("build.id")),
    db.Column("architecture_id", db.Integer(), db.ForeignKey("architecture.id")),
)


class Build(db.Model):
    __tablename__ = "build"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    version_id = db.Column(db.Integer, db.ForeignKey("version.id"), nullable=False)
    firmware_min_id = db.Column(
        db.Integer, db.ForeignKey("firmware.id"), nullable=False
    )
    firmware_max_id = db.Column(db.Integer, db.ForeignKey("firmware.id"))
    publisher_user_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    checksum = db.Column(db.Unicode(32))
    extract_size = db.Column(db.Integer)
    path = db.Column(db.Unicode(2048))
    md5 = db.Column(db.Unicode(32))
    insert_date = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    active = db.Column(db.Boolean(), default=False, nullable=False)

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
    downloads = db.relationship(
        "Download",
        back_populates="build",
        cascade="save-update, merge, delete, delete-orphan",
    )
    buildmanifest = db.relationship(
        "BuildManifest",
        back_populates="build",
        cascade="all, delete-orphan",
        uselist=False,
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

        if self.md5 is None:
            with io.open(file_path, "rb") as f:
                md5_hash = hashlib.md5()
                for chunk in iter(lambda: f.read(4096), b""):
                    md5_hash.update(chunk)
                return md5_hash.hexdigest()

        return self.md5

    def _after_insert(self):
        assert os.path.exists(os.path.join(current_app.config["DATA_PATH"], self.path))

    def _after_delete(self):
        path = os.path.join(current_app.config["DATA_PATH"], self.path)
        if os.path.exists(path):
            os.remove(path)

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
    package_id = db.Column(db.Integer, db.ForeignKey("package.id"), nullable=False)
    version = db.Column(db.Integer, nullable=False, index=True)
    upstream_version = db.Column(db.Unicode(20), nullable=False)
    changelog = db.Column(db.UnicodeText)
    report_url = db.Column(db.Unicode(255))
    distributor = db.Column(db.Unicode(50))
    distributor_url = db.Column(db.Unicode(255))
    maintainer = db.Column(db.Unicode(50))
    maintainer_url = db.Column(db.Unicode(255))
    install_wizard = db.Column(db.Boolean)
    upgrade_wizard = db.Column(db.Boolean)
    startable = db.Column(db.Boolean)
    license = db.Column(db.UnicodeText)
    insert_date = db.Column(db.DateTime, default=db.func.now(), nullable=False)

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
    descriptions = db.relationship(
        "Description",
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
    def version_string(self):
        return self.upstream_version + "-" + str(self.version)

    @hybrid_property
    def beta(self):
        return bool(self.report_url)  # Treats None and "" as False

    @hybrid_property
    def all_builds_active(self):
        return all(b.active for b in self.builds)

    @hybrid_property
    def any_builds_active(self):
        return any(b.active for b in self.builds)

    @all_builds_active.expression
    def all_builds_active(cls):
        return (
            db.select(db.func.count())
            .where(db.and_(Build.version_id == cls.id, Build.active))
            .label("active_builds")
        ) == (
            db.select(db.func.count())
            .where(Build.version_id == cls.id)
            .label("total_builds")
        )

    @beta.expression
    def beta(cls):
        return db.and_(cls.report_url.isnot(None), cls.report_url != "")

    @property
    def path(self):
        return os.path.join(self.package.name, str(self.version))

    def _after_insert(self):
        assert os.path.exists(os.path.join(current_app.config["DATA_PATH"], self.path))

    def _after_delete(self):
        path = os.path.join(current_app.config["DATA_PATH"], self.path)
        if os.path.exists(path):
            shutil.rmtree(path)

    def __str__(self):
        return self.version_string

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.version_string}>"

    @hybrid_property
    def builds_per_dsm(self):
        result = {}
        for build in self.builds:
            result.setdefault(build.firmware_min.version[0:1], []).append(build)
        return result


class Package(db.Model):
    __tablename__ = "package"

    # Columns
    id = db.Column(db.Integer, primary_key=True)
    author_user_id = db.Column(
        db.Integer, db.ForeignKey("user.id", ondelete="SET NULL")
    )
    name = db.Column(db.Unicode(50), nullable=False)
    insert_date = db.Column(db.DateTime, default=db.func.now(), nullable=False)
    download_count = db.column_property(
        db.select(db.func.count(Download.id))
        .select_from(Download.__table__.join(Build).join(Version))
        .where(Version.package_id == id)
        .scalar_subquery(),
        deferred=True,
    )
    recent_download_count = db.column_property(
        db.select(db.func.count(Download.id))
        .select_from(Download.__table__.join(Build).join(Version))
        .where(
            db.and_(
                Version.package_id == id,
                Download.date >= datetime.now() - timedelta(days=90),
            )
        )
        .correlate_except(Download)
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

    # Constraints
    __table_args__ = (db.UniqueConstraint(name),)

    @hybrid_property
    def any_builds_active(self):
        return any(v.any_builds_active for v in self.versions)

    @classmethod
    def find(cls, name):
        return cls.query.filter(cls.name == name).first()

    def __str__(self):
        return self.name

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.name}>"


@track_modifications.models_committed.connect
def on_models_committed(sender, changes):
    for obj, change in changes:
        if change == "insert" and hasattr(obj, "_after_insert"):
            obj._after_insert()
        elif change == "delete" and hasattr(obj, "_after_delete"):
            obj._after_delete()


@track_modifications.before_models_committed.connect
def on_before_models_committed(sender, changes):
    for obj, change in changes:
        if change == "insert" and hasattr(obj, "_before_insert"):
            obj._before_insert()
        elif change == "delete" and hasattr(obj, "_before_delete"):
            obj._before_delete()
