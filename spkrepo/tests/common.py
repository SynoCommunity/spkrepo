# -*- coding: utf-8 -*-
import base64
import datetime
import hashlib
import io
import itertools
import json
import os
import random
import shutil
import subprocess
import tarfile
import tempfile
from configparser import ConfigParser
from contextlib import contextmanager

import factory
import factory.alchemy
import factory.fuzzy
import faker
from factory.alchemy import SQLAlchemyModelFactory
from flask import current_app, url_for
from flask_testing import TestCase

from spkrepo import create_app
from spkrepo.ext import db
from spkrepo.models import (
    Architecture,
    Build,
    Description,
    DisplayName,
    Download,
    Firmware,
    Icon,
    Language,
    Package,
    Role,
    Screenshot,
    Service,
    User,
    Version,
)
from spkrepo.utils import populate_db

fake = faker.Faker()


class QueryFactory(factory.DictFactory):
    timezone = fake.timezone().split("/")[1]
    language = factory.LazyAttribute(
        lambda x: random.choice([language.code for language in Language.query.all()])
    )
    arch = factory.LazyAttribute(
        lambda x: random.choice(
            [
                Architecture.to_syno.get(a.code, a.code)
                for a in Architecture.query.filter(Architecture.code != "noarch").all()
            ]
        )
    )
    build = factory.LazyAttribute(
        lambda x: random.choice([f.build for f in Firmware.query.all()])
    )
    major = factory.LazyAttribute(
        lambda x: int(Firmware.find(x.build).version.split(".")[0])
    )
    minor = factory.LazyAttribute(
        lambda x: int(Firmware.find(x.build).version.split(".")[1])
    )
    unique = factory.LazyAttribute(
        lambda x: "synology_%s_%s"
        % (
            x.arch,
            str(random.choice([1, 2, 4, 15, 18, 24]))
            + str(random.choice([12, 13, 14, 15]))
            + random.choice(["", "j", "+"]),
        )
    )
    package_update_channel = factory.fuzzy.FuzzyChoice(["stable", "beta"])


class UserFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = User

    id = factory.Sequence(lambda n: n)
    username = factory.LazyAttribute(lambda x: fake.user_name())
    email = factory.LazyAttribute(lambda x: fake.email())
    password = factory.LazyAttribute(lambda x: fake.password())
    api_key = factory.LazyAttribute(lambda x: fake.md5())
    github_access_token = None
    active = True
    confirmed_at = datetime.datetime.now()


class IconFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = Icon

    id = factory.Sequence(lambda n: n)
    size = factory.fuzzy.FuzzyChoice(["72", "120"])


class ScreenshotFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = Screenshot

    id = factory.Sequence(lambda n: n)


class DisplayNameFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = DisplayName

    language = factory.LazyAttribute(lambda x: Language.find("enu"))
    displayname = factory.LazyAttribute(lambda x: " ".join(fake.words(nb=2)).title())


class DescriptionFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = Description

    language = factory.LazyAttribute(lambda x: Language.find("enu"))
    description = factory.LazyAttribute(lambda x: " ".join(fake.sentences(nb=5)))


class PackageFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = Package

    id = factory.Sequence(lambda n: n)
    name = factory.Sequence(lambda n: "test_%d" % n)

    @factory.post_generation
    def add_screenshot(self, create, extracted, **kwargs):
        if extracted is None or extracted:
            if not self.screenshots:
                screenshot_path = os.path.join(self.name, "screenshot_0.png")
                self.screenshots.append(
                    ScreenshotFactory.simple_generate(create, path=screenshot_path)
                )

    @classmethod
    def _after_postgeneration(cls, obj, create, results=None):
        if not create:
            return
        os.mkdir(os.path.join(current_app.config["DATA_PATH"], obj.name))
        for screenshot in obj.screenshots:
            screenshot_path = os.path.join(
                current_app.config["DATA_PATH"], screenshot.path
            )
            if not os.path.exists(screenshot_path):
                screenshot.save(create_image("Screenshot %s" % obj.name))


class VersionFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = Version

    id = factory.Sequence(lambda n: n)
    package = factory.SubFactory(PackageFactory)
    version = factory.Sequence(lambda n: n)
    upstream_version = factory.LazyAttribute(
        lambda x: "%d.%d.%d"
        % (fake.random_int(0, 5), fake.random_int(0, 10), fake.random_int(0, 15))
    )
    changelog = factory.LazyAttribute(lambda x: fake.sentence())
    report_url = factory.LazyAttribute(lambda x: fake.url())
    distributor = factory.LazyAttribute(lambda x: fake.name())
    distributor_url = factory.LazyAttribute(lambda x: fake.url())
    maintainer = factory.LazyAttribute(lambda x: fake.name())
    maintainer_url = factory.LazyAttribute(lambda x: fake.url())
    dependencies = factory.LazyAttribute(lambda x: fake.word())
    conf_dependencies = factory.LazyAttribute(
        lambda x: json.dumps({fake.word(): {"dsm_min_ver": "5.0-4300"}})
    )
    conflicts = factory.LazyAttribute(lambda x: fake.word())
    conf_conflicts = factory.LazyAttribute(
        lambda x: json.dumps({fake.word(): {"dsm_min_ver": "5.0-4300"}})
    )
    conf_privilege = factory.LazyAttribute(
        lambda x: json.dumps({"defaults": {"run-as": "root"}})
    )
    conf_resource = factory.LazyAttribute(
        lambda x: json.dumps(
            {
                "usr-local-linker": {
                    "lib": ["lib/foo"],
                    "bin": ["bin/foo"],
                    "etc": ["etc/foo"],
                }
            }
        )
    )
    install_wizard = False
    upgrade_wizard = False
    startable = None
    license = factory.LazyAttribute(lambda x: fake.text())
    service_dependencies = factory.LazyAttribute(
        lambda x: [random.choice(Service.query.all())]
    )

    @factory.post_generation
    def add_displayname(self, create, extracted, **kwargs):
        if extracted is None or extracted:
            if "enu" not in self.displaynames:
                displayname = self.package.name.replace("_", " ").title()
                self.displaynames["enu"] = DisplayNameFactory.simple_generate(
                    create, language=Language.find("enu"), displayname=displayname
                )

    @factory.post_generation
    def add_description(self, create, extracted, **kwargs):
        if extracted is None or extracted:
            if "enu" not in self.descriptions:
                self.descriptions["enu"] = DescriptionFactory.simple_generate(
                    create, language=Language.find("enu")
                )

    @factory.post_generation
    def add_icon(self, create, extracted, **kwargs):
        if extracted is None or extracted:
            if "72" not in self.icons:
                icon_path = os.path.join(
                    self.package.name, str(self.version), "icon_72.png"
                )
                self.icons["72"] = IconFactory.simple_generate(
                    create, path=icon_path, size="72"
                )

    @classmethod
    def _after_postgeneration(cls, obj, create, results=None):
        if not create:
            return
        os.mkdir(
            os.path.join(
                current_app.config["DATA_PATH"], obj.package.name, str(obj.version)
            )
        )
        for size, icon in obj.icons.items():
            icon_path = os.path.join(current_app.config["DATA_PATH"], icon.path)
            if not os.path.exists(icon_path):
                icon.save(create_icon(obj.displaynames["enu"].displayname, int(size)))


class BuildFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = Build

    version = factory.SubFactory(VersionFactory)
    firmware = factory.LazyAttribute(lambda x: random.choice(Firmware.query.all()))
    architectures = factory.LazyAttribute(
        lambda x: [
            random.choice(
                Architecture.query.filter(Architecture.code != "noarch").all()
            )
        ]
    )

    @factory.post_generation
    def create_spk(self, create, extracted, **kwargs):
        if not create:
            return
        build_filename = Build.generate_filename(
            self.version.package, self.version, self.firmware, self.architectures
        )
        self.path = os.path.join(
            self.version.package.name, str(self.version.version), build_filename
        )
        with create_spk(self) as spk_stream:
            self.save(spk_stream)
            if self.md5 is None:
                spk_stream.seek(0)
                self.md5 = hashlib.md5(spk_stream.read()).hexdigest()
        spk_stream.close()

    @classmethod
    def create_batch(cls, size, **kwargs):
        if (
            "version" in kwargs
            and "firmware" not in kwargs
            and "architectures" not in kwargs
        ):
            combinations = itertools.product(
                Firmware.query.all(),
                Architecture.query.filter(Architecture.code != "noarch").all(),
            )
            batch = []
            for _ in range(size):
                firmware, architecture = next(combinations)
                batch.append(
                    cls.create(
                        architectures=[architecture], firmware=firmware, **kwargs
                    )
                )
            return batch
        return super(BuildFactory, cls).create_batch(size, **kwargs)


class DownloadFactory(SQLAlchemyModelFactory):
    class Meta:
        sqlalchemy_session = db.session
        model = Download

    id = factory.Sequence(lambda n: n)
    build = factory.SubFactory(BuildFactory)
    architecture = factory.LazyAttribute(lambda x: x.build.architectures[0])
    firmware_build = factory.LazyAttribute(
        lambda x: random.choice([f.build for f in Firmware.query.all()])
    )
    ip_address = factory.LazyAttribute(lambda x: fake.ipv4())
    user_agent = factory.LazyAttribute(lambda x: fake.user_agent())
    date = factory.LazyAttribute(lambda x: fake.date_time_this_month())


# Base test case
class BaseTestCase(TestCase):
    DEBUG = False
    TESTING = True
    LOGIN_DISABLED = False
    WTF_CSRF_ENABLED = False
    DATA_PATH = tempfile.mkdtemp("spkrepo")
    SQLALCHEMY_ECHO = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///%s/test.db" % DATA_PATH
    CACHE_NO_NULL_WARNING = True

    def create_app(self):
        return create_app(config=self)

    def setUp(self):
        if not os.path.exists(self.DATA_PATH):
            os.mkdir(self.DATA_PATH)
        db.drop_all()
        db.create_all()
        populate_db()
        db.session.commit()
        db.session.autoflush = False

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.session.autoflush = True
        shutil.rmtree(self.DATA_PATH)

    def login(self, email, password):
        """
        Perform a login action

        :param email: email of the user
        :param password: password of the user
        :return: the response
        """
        return self.client.post(
            url_for("security.login"),
            data=dict(email=email, password=password),
            follow_redirects=True,
        )

    def logout(self):
        """
        Perform a logout action

        :return: the response
        """
        return self.client.get(url_for("security.logout"), follow_redirects=True)

    def create_user(self, *args, **kwargs):
        """
        Create a user with the given roles

        :param args: role names for the created user
        :param kwargs: attributes to pass to the :class:`UserFactory`
        :return: the created user
        """
        user = UserFactory(
            roles=[Role.query.filter_by(name=role).one() for role in args], **kwargs
        )
        db.session.commit()
        return user

    @contextmanager
    def logged_user(self, *args, **kwargs):
        """
        Create a user with the given roles and perform login action

        :param args: role names for the created user
        :param kwargs: attributes to pass to the :class:`UserFactory`
        :return: the logged user
        """
        user = self.create_user(*args, **kwargs)
        self.login(user.email, user.password)
        yield user
        self.logout()

    def assert201(self, response, message=None):
        """
        Check if response status code is 201

        :param response: Flask response
        :param message: Message to display on test failure
        """

        self.assertStatus(response, 201, message)

    def assert302(self, response, message=None):
        """
        Check if response status code is 302

        :param response: Flask response
        :param message: Message to display on test failure
        """

        self.assertStatus(response, 302, message)

    def assertRedirectsTo(self, response, location, message=None):
        """
        Check if response is a redirect

        :param response: Flask response
        :param location: the redirect location
        :param message: Message to display on test failure
        """

        self.assertRedirects(response, location, message)

    def assert409(self, response, message=None):
        """
        Check if response status code is 409

        :param response: Flask response
        :param message: Message to display on test failure
        """

        self.assertStatus(response, 409, message)

    def assert422(self, response, message=None):
        """
        Check if response status code is 422

        :param response: Flask response
        :param message: Message to display on test failure
        """

        self.assertStatus(response, 422, message)

    def assertHeader(self, response, header, value, message=None):
        """
        Check a response header value

        :param response: Flask response
        :param header: Header name
        :param value: Expected value of the header
        :param message: Message to display on test failure
        """

        self.assertIn(header, response.headers, message)
        self.assertEqual(response.headers[header], value, message)


def create_info(build):
    """
    Create a dict to emulate the INFO file of a SPK

    :param build: build to use to construct the info dict
    :type build: :class:`~spkrepo.models.Build`
    :return: the info dict
    """
    info = {
        "package": build.version.package.name,
        "version": build.version.version_string,
        "arch": " ".join(
            Architecture.to_syno.get(a.code, a.code) for a in build.architectures
        ),
        "displayname": build.version.displaynames["enu"].displayname,
        "description": build.version.descriptions["enu"].description,
        "firmware": build.firmware.firmware_string,
    }
    if build.version.changelog:
        info["changelog"] = build.version.changelog
    if build.version.report_url:
        info["report_url"] = build.version.report_url
    if build.version.distributor:
        info["distributor"] = build.version.distributor
    if build.version.distributor_url:
        info["distributor_url"] = build.version.distributor_url
    if build.version.maintainer:
        info["maintainer"] = build.version.maintainer
    if build.version.maintainer_url:
        info["maintainer_url"] = build.version.maintainer_url
    if build.version.dependencies:
        info["install_dep_packages"] = build.version.dependencies
    if build.version.conflicts:
        info["install_conflict_packages"] = build.version.conflicts
    if build.version.service_dependencies:
        info["install_dep_services"] = ":".join(
            [s.code for s in build.version.service_dependencies]
        )
    if build.version.startable is not None:
        info["startable"] = "yes" if build.version.startable else "no"
    for language, displayname in build.version.displaynames.items():
        info["displayname_%s" % language] = displayname.displayname
    for language, description in build.version.descriptions.items():
        info["description_%s" % language] = description.description
    if (
        build.version.conf_dependencies is not None
        or build.version.conf_conflicts is not None
    ):
        info["support_conf_folder"] = "yes"
    return info


def create_icon(text, size=72):
    """
    Create a square icon with some `text` and the given `size`

    :param text: text to display in the icon
    :param int size: size of the icon
    :return: the icon stream
    """
    return create_image(text, size, size)


def create_image(text, width=640, height=480):
    """
    Create a image with some `text` and the given `width` and `height`

    :param text: text to display in the image
    :param int width: width of the image
    :param int height: height of the image
    :return: the image stream
    """
    command = [
        "convert",
        "-size",
        "%dx%d" % (width, height),
        "canvas:none",
        "-gravity",
        "Center",
        "-fill",
        "grey",
        "-draw",
        "roundRectangle 0,0 %d,%d 15,15" % (width, height),
        "-fill",
        "black",
        "-pointsize",
        "12",
        "-draw",
        "text 0,0 '%s'" % text,
        "png:-",
    ]
    screenshot_stream = io.BytesIO()
    process = subprocess.Popen(command, stdout=subprocess.PIPE)
    screenshot_stream.write(process.communicate()[0])
    screenshot_stream.seek(0)
    return screenshot_stream


def create_spk(
    build,
    info=None,
    signature=None,
    with_checksum=False,
    with_package_icons=True,
    with_info_icons=False,
    with_info=True,
    with_package=True,
    with_scripts=True,
    with_conf=False,
    info_encoding="utf-8",
    license_encoding="utf-8",
    signature_encoding="ascii",
    conf_dependencies_encoding="utf-8",
    conf_conflicts_encoding="utf-8",
    conf_privilege_encoding="utf-8",
    conf_resource_encoding="utf-8",
):
    """
    Create a valid SPK file

    :param build: base build on which the SPK will be built
    :type build: :class:`~spkrepo.models.Build`
    :param info: INFO dict or `None` to use the result of :func:`create_info`
    :type info: dict or io.BytesIO
    :param signature: content of the syno_signature.asc file, if any
    :param bool with_checksum: whether to include the checksum in the INFO
    :param bool with_package_icons: whether to include the icons in the SPK
    :param bool with_info_icons: whether to include the icons in the INFO
    :param bool with_info: whether to include the INFO file
    :param bool with_package: whether to include the package.tgz file
    :param bool with_scripts: whether to include the scripts folder
    :param bool with_conf: whether to include the conf folder
    :param info_encoding: encoding for the INFO file
    :param license_encoding: encoding for the LICENSE file
    :param signature_encoding: encoding for the syno_signature.asc file
    :param conf_dependencies_encoding: encoding for the conf/PKG_DEPS file
    :param conf_conflicts_encoding: encoding for the conf/PKG_CONX file
    :param conf_privilege_encoding: encoding for the conf/privilege file
    :param conf_resource_encoding: encoding for the conf/resource file
    :return: the created SPK stream
    """
    # generate an info if none is given
    info = info or create_info(build)

    # open structure
    spk_stream = io.BytesIO()
    spk = tarfile.TarFile(fileobj=spk_stream, mode="w")

    # license
    if build.version.license:
        license_stream = io.BytesIO(build.version.license.encode(license_encoding))
        license_tarinfo = tarfile.TarInfo("LICENSE")
        license_stream.seek(0, io.SEEK_END)
        license_tarinfo.size = license_stream.tell()
        license_stream.seek(0)
        spk.addfile(license_tarinfo, fileobj=license_stream)

    # signature
    if signature is not None:
        signature_stream = io.BytesIO(signature.encode(signature_encoding))
        signature_tarinfo = tarfile.TarInfo("syno_signature.asc")
        signature_stream.seek(0, io.SEEK_END)
        signature_tarinfo.size = signature_stream.tell()
        signature_stream.seek(0)
        spk.addfile(signature_tarinfo, fileobj=signature_stream)

    # conf
    if (
        with_conf
        or build.version.conf_dependencies is not None
        or build.version.conf_conflicts is not None
        or build.version.conf_privilege is not None
        or build.version.conf_resource is not None
    ):
        conf_folder_tarinfo = tarfile.TarInfo("conf")
        conf_folder_tarinfo.type = tarfile.DIRTYPE
        conf_folder_tarinfo.mode = 0o755
        spk.addfile(conf_folder_tarinfo)
        if build.version.conf_dependencies is not None:
            conf_tarinfo = tarfile.TarInfo("conf/PKG_DEPS")
            config = ConfigParser()
            config.read_dict(json.loads(build.version.conf_dependencies))
            conf_stream = io.StringIO()
            config.write(conf_stream)
            conf_stream_bytes = io.BytesIO(
                conf_stream.getvalue().encode(conf_dependencies_encoding)
            )
            conf_stream_bytes.seek(0, io.SEEK_END)
            conf_tarinfo.size = conf_stream_bytes.tell()
            conf_stream_bytes.seek(0)
            spk.addfile(conf_tarinfo, fileobj=conf_stream_bytes)
        if build.version.conf_conflicts is not None:
            conf_tarinfo = tarfile.TarInfo("conf/PKG_CONX")
            config = ConfigParser()
            config.read_dict(json.loads(build.version.conf_conflicts))
            conf_stream = io.StringIO()
            config.write(conf_stream)
            conf_stream_bytes = io.BytesIO(
                conf_stream.getvalue().encode(conf_conflicts_encoding)
            )
            conf_stream_bytes.seek(0, io.SEEK_END)
            conf_tarinfo.size = conf_stream_bytes.tell()
            conf_stream_bytes.seek(0)
            spk.addfile(conf_tarinfo, fileobj=conf_stream_bytes)
        if build.version.conf_privilege is not None:
            conf_tarinfo = tarfile.TarInfo("conf/privilege")
            conf_stream_bytes = io.BytesIO(
                build.version.conf_privilege.encode(conf_privilege_encoding)
            )
            conf_stream_bytes.seek(0, io.SEEK_END)
            conf_tarinfo.size = conf_stream_bytes.tell()
            conf_stream_bytes.seek(0)
            spk.addfile(conf_tarinfo, fileobj=conf_stream_bytes)
        if build.version.conf_resource is not None:
            conf_tarinfo = tarfile.TarInfo("conf/resource")
            conf_stream_bytes = io.BytesIO(
                build.version.conf_resource.encode(conf_resource_encoding)
            )
            conf_stream_bytes.seek(0, io.SEEK_END)
            conf_tarinfo.size = conf_stream_bytes.tell()
            conf_stream_bytes.seek(0)
            spk.addfile(conf_tarinfo, fileobj=conf_stream_bytes)

    # wizards
    wizards = []
    if build.version.install_wizard:
        wizards.append("install")
    if build.version.upgrade_wizard:
        wizards.append("upgrade")
    if wizards:
        wizard_folder_tarinfo = tarfile.TarInfo("WIZARD_UIFILES")
        wizard_folder_tarinfo.type = tarfile.DIRTYPE
        wizard_folder_tarinfo.mode = 0o755
        spk.addfile(wizard_folder_tarinfo)
        for wizard in wizards:
            wizard_tarinfo = tarfile.TarInfo("WIZARD_UIFILES/%s_uifile" % wizard)
            wizard_stream = io.BytesIO(wizard.encode("utf-8"))
            wizard_stream.seek(0, io.SEEK_END)
            wizard_tarinfo.size = wizard_stream.tell()
            wizard_stream.seek(0)
            spk.addfile(wizard_tarinfo, fileobj=wizard_stream)

    # scripts
    if with_scripts:
        scripts_folder_tarinfo = tarfile.TarInfo("scripts")
        scripts_folder_tarinfo.type = tarfile.DIRTYPE
        scripts_folder_tarinfo.mode = 0o755
        spk.addfile(scripts_folder_tarinfo)
        for script in (
            "preinst",
            "postinst",
            "preuninst",
            "postuninst",
            "preupgrade",
            "postupgrade",
            "start-stop-status",
        ):
            script_tarinfo = tarfile.TarInfo("scripts/%s" % script)
            script_stream = io.BytesIO(script.encode("utf-8"))
            script_stream.seek(0, io.SEEK_END)
            script_tarinfo.size = script_stream.tell()
            script_stream.seek(0)
            spk.addfile(script_tarinfo, fileobj=script_stream)

    # package
    if with_package:
        package_stream = io.BytesIO()
        package = tarfile.TarFile(fileobj=package_stream, mode="w")
        unique = "%s-%d-%d-[%s]" % (
            build.version.package.name,
            build.version.version,
            build.firmware.build,
            "-".join(a.code for a in build.architectures),
        )
        unique_stream = io.BytesIO(unique.encode("utf-8"))
        unique_tarinfo = tarfile.TarInfo("unique")
        unique_stream.seek(0, io.SEEK_END)
        unique_tarinfo.size = unique_stream.tell()
        unique_stream.seek(0)
        package.addfile(unique_tarinfo, fileobj=unique_stream)
        unique_stream.close()
        package.close()
        package_tarinfo = tarfile.TarInfo("package.tgz")
        package_stream.seek(0, io.SEEK_END)
        package_tarinfo.size = package_stream.tell()
        package_stream.seek(0)
        spk.addfile(package_tarinfo, fileobj=package_stream)
        if "checksum" not in info and with_checksum:
            checksum = hashlib.md5()
            package_stream.seek(0)
            for chunk in iter(lambda: package_stream.read(io.DEFAULT_BUFFER_SIZE), b""):
                checksum.update(chunk)
            info["checksum"] = checksum.hexdigest().decode("utf-8")
        package_stream.close()

    # icons
    if with_package_icons or with_info_icons:
        for size, icon in build.version.icons.items():
            with create_icon(build.version.package.name, int(size)) as f:
                suffix = "" if size == "72" else "_%s" % size
                if with_package_icons:
                    icon_tarinfo = tarfile.TarInfo("PACKAGE_ICON%s.PNG" % suffix)
                    f.seek(0, io.SEEK_END)
                    icon_tarinfo.size = f.tell()
                    f.seek(0)
                    spk.addfile(icon_tarinfo, fileobj=f)
                if with_info_icons:
                    f.seek(0)
                    info["package_icon%s" % suffix] = base64.b64encode(f.read()).decode(
                        "utf-8"
                    )

    # info
    if with_info:
        if isinstance(info, io.BytesIO):
            info_stream = info
        else:
            b = "\n".join(['%s="%s"' % (k, v) for k, v in info.items()]).encode(
                info_encoding
            )
            info_stream = io.BytesIO(b)
        info_tarinfo = tarfile.TarInfo("INFO")
        info_stream.seek(0, io.SEEK_END)
        info_tarinfo.size = info_stream.tell()
        info_stream.seek(0)
        spk.addfile(info_tarinfo, fileobj=info_stream)

    # close structure
    spk.close()
    spk_stream.seek(0)

    return spk_stream
