# -*- coding: utf-8 -*-
"""Pure unit tests for spkrepo.domain — no app, DB, FS, or network."""

from datetime import date

import pytest

from spkrepo.domain import access, catalog, downloads, shared_kernel, spk, upload
from spkrepo.domain import versions as _versions
from spkrepo.domain.storage_policy import cdn_purge_url, should_attempt_upload
from spkrepo.exceptions import SPKParseError


class TestSharedKernel:
    def test_translate_arch(self):
        assert shared_kernel.translate_arch_from_syno("88f6281") == "88f628x"
        assert shared_kernel.translate_arch_from_syno("x86_64") == "x86_64"

    def test_parse_firmware_ok(self):
        assert shared_kernel.parse_firmware("6.2-23739") == ("6.2", 23739)

    @pytest.mark.parametrize("bad", ["", "6.2", "x-1", "6.2-12"])
    def test_parse_firmware_bad(self, bad):
        with pytest.raises(ValueError):
            shared_kernel.parse_firmware(bad)

    def test_parse_version_ok(self):
        assert shared_kernel.parse_version("1.2.3-10") == ("1.2.3", 10)

    def test_parse_version_bad(self):
        with pytest.raises(ValueError):
            shared_kernel.parse_version("1.2.3")

    def test_build_filename(self):
        assert (
            shared_kernel.build_filename("git", 4, 42661, ["x86_64", "noarch"])
            == "git.v4.f42661[x86_64-noarch].spk"
        )

    @pytest.mark.parametrize(
        "info,expected",
        [
            ({}, True),
            ({"startable": False}, False),
            ({"ctl_stop": False}, False),
            ({"startable": True}, True),
        ],
    )
    def test_derive_startable(self, info, expected):
        assert shared_kernel.derive_startable(info) is expected

    def test_map_displaynames_bare_wins(self):
        info = {"displayname": "New", "displayname_enu": "Old", "displayname_fre": "F"}
        assert shared_kernel.map_displaynames(info) == {"enu": "New", "fre": "F"}

    def test_validate_firmware_range(self):
        shared_kernel.validate_firmware_range(100, 200)
        shared_kernel.validate_firmware_range(100, None)
        with pytest.raises(ValueError):
            shared_kernel.validate_firmware_range(200, 100)

    @pytest.mark.parametrize(
        "filename,expected",
        [
            ("pkg.v1.f42661[x86_64].spk", (42661, False)),
            ("pkg.v1.f6931[noarch].spk", (None, True)),
            ("pkg.v1.spk", (None, False)),
        ],
    )
    def test_parse_filename_target(self, filename, expected):
        assert shared_kernel.parse_filename_target(filename) == expected


class TestAccess:
    def test_fastly_wins(self):
        headers = {"Fastly-Client-IP": "1.2.3.4", "X-Forwarded-For": "9.9.9.9, 5.6.7.8"}
        assert access.resolve_client_ip(headers, "127.0.0.1") == "1.2.3.4"

    def test_xff_second_to_last(self):
        headers = {"X-Forwarded-For": "client, fastly, nginx-peer"}
        assert access.resolve_client_ip(headers, "127.0.0.1") == "fastly"

    def test_xff_single(self):
        assert access.resolve_client_ip({"X-Forwarded-For": "peer"}, "r") == "peer"

    def test_remote_fallback(self):
        assert access.resolve_client_ip({}, "127.0.0.1") == "127.0.0.1"
        assert access.resolve_client_ip({}, None) == ""


class TestUpload:
    def test_detect_conflicts_overlap(self):
        existing = [{"archs": {"x86_64"}, "min": 100, "max": 200}]
        assert upload.detect_conflicts(existing, {"x86_64"}, 150, 150) == {"x86_64"}

    def test_detect_conflicts_disjoint_fw(self):
        existing = [{"archs": {"x86_64"}, "min": 100, "max": 200}]
        assert upload.detect_conflicts(existing, {"x86_64"}, 201, 300) == set()

    def test_detect_conflicts_disjoint_arch(self):
        existing = [{"archs": {"x86_64"}, "min": 100, "max": 200}]
        assert upload.detect_conflicts(existing, {"arm"}, 150, 150) == set()

    def test_detect_conflicts_open_max(self):
        existing = [{"archs": {"x86_64"}, "min": 100, "max": None}]
        assert upload.detect_conflicts(existing, {"x86_64"}, 100, None) == {"x86_64"}
        assert upload.detect_conflicts(existing, {"x86_64"}, 101, None) == set()

    def test_authorize(self):
        upload.authorize_upload({"package_admin"}, True, False)
        upload.authorize_upload(set(), False, True)
        with pytest.raises(PermissionError):
            upload.authorize_upload(set(), True, False)
        with pytest.raises(PermissionError):
            upload.authorize_upload({"developer"}, False, False)


class TestCatalog:
    def test_firmware_in_range(self):
        assert catalog.firmware_in_range(150, 100, 200)
        assert not catalog.firmware_in_range(99, 100, 200)
        assert not catalog.firmware_in_range(201, 100, 200)
        assert catalog.firmware_in_range(100, 100, None)
        # Catalog: None max = unbounded above (no os_max_ver); contrast
        # upload.detect_conflicts where None max = single-fw point.
        assert catalog.firmware_in_range(101, 100, None)

    def test_quick_flags(self):
        assert catalog.derive_quick_flags(None, False, False, True) == (
            True,
            True,
            True,
        )
        assert catalog.derive_quick_flags("lic", False, False, True) == (
            False,
            False,
            False,
        )
        assert catalog.derive_quick_flags(None, True, False, True) == (
            False,
            True,
            False,
        )
        assert catalog.derive_quick_flags(None, False, False, False) == (
            True,
            True,
            False,
        )
        # startable None counts as not-False
        assert catalog.derive_quick_flags(None, False, False, None)[2] is True

    def test_build_entry_data_beta_and_retina(self):
        entry = catalog.build_entry_data(
            package_name="git",
            version_string="2.1.2-4",
            displayname="Git",
            description="d",
            link="L",
            thumbnails=["T"],
            snapshots=[],
            license_text=None,
            install_wizard=False,
            upgrade_wizard=False,
            startable=True,
            dependencies=None,
            conflicts=None,
            download_count=5,
            recent_download_count=1,
            report_url="http://r",
            retina_url="R",
        )
        assert entry["beta"] is True
        assert entry["thumbnail_retina"] == ["R", "R"]
        assert entry["startable"] == "yes"
        assert entry["qinst"] is True


class TestSpk:
    def test_parse_info_lines_ok(self):
        info, icons = spk.parse_info_lines(
            [
                b'package="git"',
                b'version="1.0-1"',
                b'arch="x86_64"',
                b'displayname="G"',
                b'description="d"',
                b'startable="yes"',
            ]
        )
        assert info["package"] == "git"
        assert info["startable"] is True
        assert icons == {}

    def test_parse_info_bad_line(self):
        with pytest.raises(SPKParseError):
            spk.parse_info_lines([b"not-valid"])

    def test_parse_info_bad_boolean(self):
        with pytest.raises(SPKParseError):
            spk.parse_info_lines([b'startable="maybe"'])

    def test_parse_info_bad_package(self):
        with pytest.raises(SPKParseError):
            spk.parse_info_lines([b'package="bad name!"'])

    def test_validate_required(self):
        with pytest.raises(SPKParseError):
            spk.validate_required({"package": "x"})
        spk.validate_required(
            {
                "package": "x",
                "version": "1-1",
                "arch": "a",
                "displayname": "d",
                "description": "e",
            }
        )

    def test_verify_checksum(self):
        import hashlib

        payload = b"hello"
        spk.verify_checksum(hashlib.md5(payload).hexdigest(), payload)
        with pytest.raises(SPKParseError):
            spk.verify_checksum("0" * 32, payload)


class TestDownloads:
    def test_classify(self):
        assert downloads.classify_source("x", 1) == "catalog"
        assert downloads.classify_source(None, 1) == "manual"
        assert downloads.classify_source("x", None) == "manual"

    def test_parse_today_injected(self):
        fixed = date(2020, 1, 2)
        _, _, _, rd, _, _ = downloads.parse_download({"url": "/p/1.spk"}, today=fixed)
        assert rd == fixed

    def test_aggregate_and_rows(self):
        parsed = [(("p", None, None, None, date(2020, 1, 1)), False, "manual")] * 2
        counts, noarchs, sources = downloads.aggregate_parsed(parsed)
        key = ("p", None, None, None, date(2020, 1, 1))
        assert counts[key] == 2
        rows = downloads.build_upsert_rows(counts, {key: 7}, noarchs, sources)
        assert rows[0]["count"] == 2
        assert rows[0]["build_id"] == 7


class TestStoragePolicy:
    @pytest.mark.parametrize(
        "path,exists,signed,expected",
        [
            (None, True, True, (False, "no-path")),
            ("p", False, True, (False, "missing-file")),
            ("p", True, False, (False, "unsigned")),
            ("p", True, True, (True, "ok")),
        ],
    )
    def test_should_attempt(self, path, exists, signed, expected):
        assert should_attempt_upload(path, exists, signed) == expected

    def test_cdn_url(self):
        assert cdn_purge_url("cdn.example", "/nas/x") == "https://cdn.example/nas/x"
        assert cdn_purge_url("cdn.example", "nas/x") == "https://cdn.example/nas/x"


class TestDomainGaps:
    def test_map_displaynames_suffix_only_and_empty(self):
        assert shared_kernel.map_displaynames({}) == {}
        assert shared_kernel.map_displaynames({"displayname_fre": "F"}) == {"fre": "F"}

    def test_map_descriptions(self):
        assert shared_kernel.map_descriptions({}) == {}
        info = {"description": "d", "description_fre": "f"}
        assert shared_kernel.map_descriptions(info) == {"enu": "d", "fre": "f"}

    @pytest.mark.parametrize(
        "info,expected",
        [
            ({"ctl_stop": True}, True),
            ({"startable": False, "ctl_stop": False}, False),
            ({"startable": None, "ctl_stop": None}, True),
        ],
    )
    def test_derive_startable_extra(self, info, expected):
        assert shared_kernel.derive_startable(info) is expected

    def test_firmware_range_valid(self):
        from spkrepo.domain.upload import firmware_range_valid

        assert firmware_range_valid(100, 200) is True
        assert firmware_range_valid(100, None) is True
        assert firmware_range_valid(200, 100) is False

    def test_resolve_client_ip_edge(self):
        assert access.resolve_client_ip({"X-Forwarded-For": "  "}, "r") == "r"
        assert access.resolve_client_ip({"x-forwarded-for": "a, , b,"}, "r") == "a"
        assert (
            access.resolve_client_ip({"FASTLY-CLIENT-IP": "9.9.9.9"}, "r") == "9.9.9.9"
        )

    def test_detect_conflicts_edge(self):
        assert upload.detect_conflicts([], {"x"}, 1, 1) == set()
        existing = [
            {"archs": {"a", "b"}, "min": 100, "max": 200},
            {"archs": {"b"}, "min": 300},  # missing max -> point
        ]
        assert upload.detect_conflicts(existing, {"a", "b"}, 150, None) == {"a", "b"}
        assert upload.detect_conflicts(existing, {"b"}, 300, 300) == {"b"}
        assert upload.detect_conflicts(existing, {"a"}, 250, 260) == set()

    def test_quick_flags_none_wizards(self):
        assert catalog.derive_quick_flags(None, None, None, True) == (
            False,
            False,
            False,
        )

    def test_set_if_truthy(self):
        entry: dict = {}
        catalog.set_if_truthy(entry, "k", "")
        assert entry == {}
        catalog.set_if_truthy(entry, "k", "v")
        assert entry == {"k": "v"}

    def test_build_entry_data_plain(self):
        entry = catalog.build_entry_data(
            package_name="p",
            version_string="1-1",
            displayname="D",
            description="d",
            link="L",
            thumbnails=[],
            snapshots=[],
            license_text="lic",
            install_wizard=None,
            upgrade_wizard=None,
            startable=None,
            dependencies=None,
            conflicts=None,
            download_count=0,
            recent_download_count=0,
        )
        assert "beta" not in entry
        assert "thumbnail_retina" not in entry
        assert "startable" not in entry
        assert entry["qinst"] is False

    def test_build_entry_data_startable_no(self):
        entry = catalog.build_entry_data(
            package_name="p",
            version_string="1-1",
            displayname="D",
            description="d",
            link="L",
            thumbnails=[],
            snapshots=[],
            license_text=None,
            install_wizard=False,
            upgrade_wizard=False,
            startable=False,
            dependencies=None,
            conflicts=None,
            download_count=0,
            recent_download_count=0,
            changelog="c",
            md5="m",
            size=123,
        )
        assert entry["startable"] == "no"
        assert entry["changelog"] == "c"

    def test_parse_info_lines_edge(self):
        info, _ = spk.parse_info_lines([b"", b"  ", b'foo="bar"'])
        assert info == {"foo": "bar"}
        with pytest.raises(SPKParseError):
            spk.parse_info_lines([b"\xff\xfe"])
        import base64

        payload = base64.b64encode(b"img").decode()
        info, icons = spk.parse_info_lines(
            [
                f'package_icon="{payload}"'.encode(),
                b'package="p"',
            ]
        )
        assert icons["72"] == b"img"
        with pytest.raises(SPKParseError):
            spk.parse_info_lines([b'package_icon="!!!not-b64!!!"'])

    def test_parse_conf(self):
        deps = spk.parse_conf_file(b"[a]\nk=v\n", "conf/PKG_DEPS")
        assert deps == {"a": {"k": "v"}}
        with pytest.raises(SPKParseError):
            spk.parse_conf_file(b"\xff", "conf/PKG_DEPS")
        assert spk.parse_json_conf(b'{"a": 1}', "conf/privilege") == '{"a": 1}'
        with pytest.raises(SPKParseError):
            spk.parse_json_conf(b"not-json", "conf/privilege")
        with pytest.raises(SPKParseError):
            spk.parse_json_conf(b"\xff", "conf/privilege")

    def test_is_countable_and_range(self):
        from spkrepo.domain.downloads import is_full_range

        assert is_full_range("") is True
        assert is_full_range("bytes=0-100") is True
        assert is_full_range("bytes=5-") is False
        assert (
            downloads.is_countable_download({"url": "/a.txt", "response_status": 200})
            is False
        )
        assert (
            downloads.is_countable_download(
                {"url": "/a.spk", "response_status": 206, "range": "bytes=5-"}
            )
            is False
        )

    def test_is_countable_positive_paths(self):
        assert (
            downloads.is_countable_download({"url": "/p/1.spk", "response_status": 200})
            is True
        )
        assert (
            downloads.is_countable_download(
                {"url": "/p/1.spk?a=1", "response_status": 200}
            )
            is True
        )
        assert (
            downloads.is_countable_download(
                {"url": "/p/1.spk", "response_status": 206, "range": "bytes=0-99"}
            )
            is True
        )
        assert (
            downloads.is_countable_download({"url": "/p/1.spk", "response_status": 206})
            is True
        )
        assert (
            downloads.is_countable_download({"url": "/p/1.spk", "response_status": 404})
            is False
        )

    def test_parse_download_valid_path(self):
        from datetime import date as _date

        url_path, arch, fw, rd, tfw, noarch = downloads.parse_download(
            {
                "url": "/sab/81/sab.v81.f42661%5Bx86_64%5D.spk?x=1",
                "arch": "x86_64",
                "build": "1594",
                "timestamp": "2026-06-14T10:53:08",
            }
        )
        assert url_path == "sab/81/sab.v81.f42661[x86_64].spk"
        assert arch == "x86_64"
        assert fw == 1594
        assert rd == _date(2026, 6, 14)
        assert tfw == 42661
        assert noarch is False

    def test_parse_info_icon_sizes_and_bools(self):
        import base64 as _b64

        payload = _b64.b64encode(b"img").decode()
        info, icons = spk.parse_info_lines(
            [
                f'package_icon_120="{payload}"'.encode(),
                f'package_icon_256="{payload}"'.encode(),
                b'ctl_stop="no"',
                b'support_conf_folder="yes"',
            ]
        )
        assert set(icons) == {"120", "256"}
        assert info["ctl_stop"] is False
        assert info["support_conf_folder"] is True

    def test_entry_optional_keys(self):
        entry = catalog.build_entry_data(
            package_name="p",
            version_string="1-1",
            displayname="D",
            description="d",
            link="L",
            thumbnails=[],
            snapshots=["S"],
            license_text=None,
            install_wizard=False,
            upgrade_wizard=False,
            startable=True,
            dependencies="dep",
            conflicts="con",
            download_count=0,
            recent_download_count=0,
            distributor="di",
            distributor_url="du",
            maintainer="m",
            maintainer_url="mu",
        )
        assert entry["snapshot"] == ["S"]
        assert entry["deppkgs"] == "dep"
        assert entry["distributor"] == "di"

    def test_group_empty_and_nondigit(self):
        from spkrepo.domain.catalog import _firmware_sort_key
        from spkrepo.domain.catalog import group_builds_per_dsm as _group

        assert _group([]) == {}
        assert _firmware_sort_key("7.x") == (7, "x")

    def test_loose_info_text(self):
        from spkrepo.domain.spk import parse_loose_info_text

        assert parse_loose_info_text("") == {}
        assert parse_loose_info_text('a="1"\nbad-line\nc = 3\n = x') == {
            "a": "1",
            "c": "3",
        }

    def test_has_wizard_variants(self):
        from spkrepo.domain.spk import has_wizard

        assert has_wizard(["WIZARD_UIFILES/install_uifile"], "install") is True
        assert has_wizard(["WIZARD_UIFILES/install_uifile_enu"], "install") is True
        assert has_wizard(["WIZARD_UIFILES/install_uifile.sh"], "install") is True
        assert has_wizard(["WIZARD_UIFILES/upgrade_uifile"], "install") is False
        assert has_wizard(["WIZARD_UIFILES/uninstall_uifile"], "uninstall") is True
        assert has_wizard(["WIZARD_UIFILES/uninstall_uifile_enu"], "uninstall") is True
        assert has_wizard(["WIZARD_UIFILES/uninstall_uifile.sh"], "uninstall") is True
        assert has_wizard([], "install") is False

    def test_derive_startable_raw(self):
        from spkrepo.domain.spk import derive_startable_raw

        assert derive_startable_raw({}) is True
        assert derive_startable_raw({"startable": "no"}) is False
        assert derive_startable_raw({"ctl_stop": "no"}) is False
        assert derive_startable_raw({"startable": "yes"}) is True

    def test_extract_version_metadata_truth_table(self):
        """Fake-based pins for extract_version_metadata (domain-owned)."""
        import types

        def _spk(info, wizards=frozenset(), license=None):
            return types.SimpleNamespace(
                info=info, wizards=set(wizards), license=license
            )

        m = _versions.extract_version_metadata(
            _spk(
                {
                    "version": "1.2.3-10",
                    "displayname": "G",
                    "install_dep_services": "a b",
                }
            )
        )
        assert m["displaynames"] == {"enu": "G"}
        assert m["upstream_version"] == "1.2.3"
        assert m["install_dep_services"] == {"a", "b"}
        assert m["startable"] is True
        assert (
            _versions.extract_version_metadata(
                _spk({"version": "1-1", "ctl_stop": False})
            )["startable"]
            is False
        )
        assert (
            _versions.extract_version_metadata(_spk({"version": "bad"}))[
                "upstream_version"
            ]
            is None
        )
        m = _versions.extract_version_metadata(
            _spk({"version": "1-1"}, wizards={"install", "upgrade"})
        )
        assert m["install_wizard"] is True and m["upgrade_wizard"] is True

    def test_assert_version_metadata_matches_db_fakes(self):
        """Fake-based pins for the consistency check (no DB)."""
        import types

        def _svc(code):
            return types.SimpleNamespace(code=code)

        def _ver(**kw):
            base = dict(
                upstream_version="1.2.3",
                report_url=None,
                distributor=None,
                distributor_url=None,
                maintainer=None,
                maintainer_url=None,
                install_wizard=False,
                upgrade_wizard=False,
                startable=True,
                license=None,
                service_dependencies=[],
                displaynames={},
            )
            base.update(kw)
            return types.SimpleNamespace(**base)

        def _spk(info, wizards=frozenset(), license=None):
            return types.SimpleNamespace(
                info=info, wizards=set(wizards), license=license
            )

        ok_info = {"version": "1.2.3-4", "displayname": "G"}
        ok_spk = _spk(ok_info)
        _versions.assert_version_metadata_matches_db(
            _ver(displaynames={"enu": types.SimpleNamespace(displayname="G")}),
            ok_spk,
        )
        with pytest.raises(ValueError, match="displaynames"):
            _versions.assert_version_metadata_matches_db(
                _ver(displaynames={"enu": types.SimpleNamespace(displayname="X")}),
                ok_spk,
            )
        with pytest.raises(ValueError, match="upstream_version"):
            _versions.assert_version_metadata_matches_db(
                _ver(
                    upstream_version="9.9.9",
                    displaynames={"enu": types.SimpleNamespace(displayname="G")},
                ),
                ok_spk,
            )
        with pytest.raises(ValueError, match="service_dependencies"):
            _versions.assert_version_metadata_matches_db(
                _ver(
                    displaynames={"enu": types.SimpleNamespace(displayname="G")},
                    service_dependencies=[_svc("apache-web")],
                ),
                ok_spk,
            )
        # each remaining simple field mismatch is reported by name
        for field, spk_val in [
            ("report_url", "http://r"),
            ("distributor", "d"),
            ("distributor_url", "http://d"),
            ("maintainer", "m"),
            ("maintainer_url", "http://m"),
        ]:
            with pytest.raises(ValueError, match=field):
                _versions.assert_version_metadata_matches_db(
                    _ver(displaynames={"enu": types.SimpleNamespace(displayname="G")}),
                    _spk(dict(ok_info, **{field: spk_val})),
                )
        with pytest.raises(ValueError, match="license"):
            _versions.assert_version_metadata_matches_db(
                _ver(displaynames={"enu": types.SimpleNamespace(displayname="G")}),
                _spk(ok_info, license="lic"),
            )
        with pytest.raises(ValueError, match="install_wizard"):
            _versions.assert_version_metadata_matches_db(
                _ver(displaynames={"enu": types.SimpleNamespace(displayname="G")}),
                _spk(ok_info, wizards={"install"}),
            )
        with pytest.raises(ValueError, match="upgrade_wizard"):
            _versions.assert_version_metadata_matches_db(
                _ver(displaynames={"enu": types.SimpleNamespace(displayname="G")}),
                _spk(ok_info, wizards={"upgrade"}),
            )
        # startable=None in DB means default-true, matching a key-omitting SPK
        _versions.assert_version_metadata_matches_db(
            _ver(
                startable=None,
                displaynames={"enu": types.SimpleNamespace(displayname="G")},
            ),
            _spk({"version": "1.2.3-4", "displayname": "G"}),
        )

    def test_branch_gaps(self):
        from spkrepo.domain import catalog as _cat
        from spkrepo.domain import downloads as _dl
        from spkrepo.domain import shared_kernel as _sk
        from spkrepo.domain import spk as _spk

        # parse_upstream_lenient: strict ok + malformed fallback
        assert _sk.parse_upstream_lenient("1.2.3-10") == "1.2.3"
        assert _sk.parse_upstream_lenient("bad") == "bad"
        assert _sk.parse_upstream_lenient("") == ""
        # non-digit major sort branch (defensive; real majors are numeric)
        from spkrepo.domain.catalog import group_builds_per_dsm as _group2

        def _b2(v):
            return type("B", (), {"firmware_min": type("F", (), {"version": v})()})()

        assert list(_group2([_b2("SRM")]).keys()) == ["SRM"]
        assert list(_group2([_b2("SRM"), _b2("DSM")]).keys()) == ["SRM", "DSM"]
        # ARCH_TO_SYNO write-direction map pinned
        assert _sk.ARCH_TO_SYNO["88f628x"] == "88f6281"

        # map_descriptions custom prefix
        assert _sk.map_descriptions({"x_enu": "d"}, prefix="x_") == {"enu": "d"}
        # parse_version None/empty
        with pytest.raises(ValueError):
            _sk.parse_version(None)
        with pytest.raises(ValueError):
            _sk.parse_version("")
        # filename multi/mixed/empty
        assert _sk.parse_filename_target("p.v1.f1[a-b].spk") == (1, False)
        assert _sk.parse_filename_target("p.v1.f1[noarch-x].spk") == (None, True)
        assert _sk.parse_filename_target("") == (None, False)
        assert _sk.parse_filename_target(None) == (None, False)
        # license "" is not None -> flags False
        assert _cat.derive_quick_flags("", False, False, True) == (False, False, False)
        # falsy optionals omitted, empty report_url -> no beta
        e = _cat.build_entry_data(
            package_name="p",
            version_string="1-1",
            displayname="D",
            description="d",
            link="L",
            thumbnails=[],
            snapshots=[],
            license_text=None,
            install_wizard=False,
            upgrade_wizard=False,
            startable=True,
            dependencies=None,
            conflicts=None,
            download_count=0,
            recent_download_count=0,
            report_url="",
            md5="",
            size=0,
            retina_url="",
        )
        assert "beta" not in e and "md5" not in e and "thumbnail_retina" not in e
        # icon size fall-through -> generic info key
        info, icons = _spk.parse_info_lines([b'package_icon_999="x"'])
        assert icons == {} and info["package_icon_999"] == "x"
        # support_conf_folder=no parses False
        info, _ = _spk.parse_info_lines([b'support_conf_folder="no"'])
        assert info["support_conf_folder"] is False
        # malformed INI -> SPKParseError
        with pytest.raises(SPKParseError):
            _spk.parse_conf_file(b"no-section-header\n", "conf/PKG_DEPS")
        # has_wizard uninstall + combo suffix
        assert _spk.has_wizard(["WIZARD_UIFILES/uninstall_uifile"], "uninstall") is True
        assert (
            _spk.has_wizard(["WIZARD_UIFILES/install_uifile_enu.sh"], "install") is True
        )
        # loose parse None
        assert _spk.parse_loose_info_text(None) == {}
        # is_full_range None (missing header -> countable) + missing status
        assert _dl.is_full_range(None) is True
        assert _dl.is_countable_download({"url": "/a.spk"}) is False
        assert (
            _dl.is_countable_download({"url": "/a.spk", "response_status": "200"})
            is False
        )
        # parse_download no-slash URL, pre-int build, missing timestamp key
        p, _, fw, rd, _, _ = _dl.parse_download(
            {"url": "pkg.spk", "build": 1594}, today=date(2020, 1, 1)
        )
        assert p == "pkg.spk" and fw == 1594 and rd == date(2020, 1, 1)
        # aggregate multi-key last-write + upsert True propagation
        k1 = ("p", 1, 1, 1, date(2020, 1, 1))
        k2 = ("p", 2, 2, 2, date(2020, 1, 2))
        counts, noarchs, sources = _dl.aggregate_parsed(
            [(k1, False, "catalog"), (k1, True, "manual"), (k2, False, "catalog")]
        )
        assert counts[k1] == 2 and noarchs[k1] is True and sources[k1] == "manual"
        rows = _dl.build_upsert_rows(counts, {}, noarchs, sources)
        assert (
            next(r for r in rows if r["date"] == date(2020, 1, 1))["target_noarch"]
            is True
        )

    def test_parse_download_coercion(self):
        _, arch, fw, _, tfw, noarch = downloads.parse_download(
            {
                "url": "/p/1.spk?x=1",
                "arch": "",
                "build": "bad",
                "timestamp": "bad",
            },
            today=date(2021, 5, 6),
        )
        assert arch is None
        assert fw is None
        assert tfw is None
        assert noarch is False

    def test_aggregate_empty_and_defaults(self):
        counts, noarchs, sources = downloads.aggregate_parsed([])
        assert counts == {}
        rows = downloads.build_upsert_rows(counts, {}, noarchs, sources)
        assert rows == []
        key = ("p", None, None, None, date(2021, 1, 1))
        rows = downloads.build_upsert_rows({key: 1}, {}, {}, {})
        assert rows[0]["build_id"] is None
        assert rows[0]["target_noarch"] is False
        assert rows[0]["download_source"] == "catalog"

    def test_group_builds_per_dsm(self):
        from spkrepo.domain.catalog import group_builds_per_dsm

        def _b(v):
            return type("B", (), {"firmware_min": type("F", (), {"version": v})()})()

        groups = group_builds_per_dsm([_b("7.1"), _b("6.2"), _b("7.2")])
        assert list(groups.keys()) == ["7", "6"]
        assert [b.firmware_min.version for b in groups["7"]] == ["7.2", "7.1"]

    def test_residual_edge_pins(self):
        # Second syno spelling; today=None fallback; falsy-0 coercion;
        # raw startable case; empty conf; duplicate keys; None displayname;
        # empty arch list; 3-part sort; upgrade symmetry; falsy set_if_truthy.
        assert shared_kernel.translate_arch_from_syno("88f6282") == "88f628x"
        _, _, _, rd, _, _ = downloads.parse_download({"url": "/p/1.spk"})
        assert rd == date.today()
        _, arch, fw, _, _, _ = downloads.parse_download(
            {"url": "/p/1.spk", "arch": 0, "build": 0},
            today=date(2020, 1, 1),
        )
        assert arch is None and fw is None
        from spkrepo.domain.spk import derive_startable_raw

        assert derive_startable_raw({"startable": "No"}) is True
        from spkrepo.domain.spk import parse_conf_file

        assert parse_conf_file(b"", "conf/PKG_DEPS") == {}
        info, _ = spk.parse_info_lines([b'foo="a"', b'foo="b"'])
        assert info["foo"] == "b"
        assert shared_kernel.map_displaynames({"displayname": None}) == {}
        assert shared_kernel.map_displaynames({"displayname": ""}) == {}
        assert shared_kernel.build_filename("p", 1, 1, []) == "p.v1.f1[].spk"
        from spkrepo.domain.catalog import _firmware_sort_key

        assert _firmware_sort_key("7.2.1") == (7, 2, 1)
        assert catalog.derive_quick_flags(None, False, True, True) == (
            True,
            False,
            True,
        )
        entry: dict = {}
        catalog.set_if_truthy(entry, "a", 0)
        catalog.set_if_truthy(entry, "b", None)
        catalog.set_if_truthy(entry, "c", False)
        assert entry == {}
