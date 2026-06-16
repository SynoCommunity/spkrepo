# -*- coding: utf-8 -*-
from datetime import date

from spkrepo.cli import is_countable_download, parse_download


class TestIsCountableDownload:
    def test_spk_url_200(self):
        assert is_countable_download(
            {"url": "/pkg/1/pkg.v1.spk", "response_status": 200}
        )

    def test_spk_url_206_no_range(self):
        assert is_countable_download(
            {"url": "/pkg/1/pkg.v1.spk", "response_status": 206, "range": ""}
        )

    def test_spk_url_206_full_range(self):
        assert is_countable_download(
            {
                "url": "/pkg/1/pkg.v1.spk",
                "response_status": 206,
                "range": "bytes=0-1048575",
            }
        )

    def test_spk_url_206_partial_range(self):
        assert not is_countable_download(
            {
                "url": "/pkg/1/pkg.v1.spk",
                "response_status": 206,
                "range": "bytes=1048576-",
            }
        )

    def test_non_spk_url(self):
        assert not is_countable_download(
            {"url": "/some/other/file.txt", "response_status": 200}
        )

    def test_404_status(self):
        assert not is_countable_download(
            {"url": "/pkg/1/pkg.v1.spk", "response_status": 404}
        )

    def test_301_redirect(self):
        assert not is_countable_download(
            {"url": "/pkg/1/pkg.v1.spk", "response_status": 301}
        )


class TestParseDownload:
    def test_catalog_download(self):
        url_path, arch_code, fw, rd, target_fw, noarch = parse_download(
            {
                "url": "/sabnzbd/81/sabnzbd.v81.f42661%5Bapollolake-avoton%5D.spk",
                "arch": "geminilake",
                "build": "86009",
                "response_status": 200,
                "timestamp": "2026-06-14T10:53:08+0000",
            }
        )
        assert url_path == "sabnzbd/81/sabnzbd.v81.f42661[apollolake-avoton].spk"
        assert arch_code == "geminilake"
        assert fw == 86009
        assert rd == date(2026, 6, 14)
        assert target_fw == 42661
        assert noarch is False

    def test_manual_download(self):
        url_path, arch_code, fw, rd, target_fw, noarch = parse_download(
            {
                "url": "/sabnzbd/81/sabnzbd.v81.f42661%5Bapollolake-avoton%5D.spk",
                "arch": "",
                "build": "",
                "response_status": 200,
                "timestamp": "2026-06-14T10:53:08+0000",
            }
        )
        assert url_path == "sabnzbd/81/sabnzbd.v81.f42661[apollolake-avoton].spk"
        assert arch_code is None
        assert fw is None

    def test_noarch_package(self):
        url_path, arch_code, fw, rd, target_fw, noarch = parse_download(
            {
                "url": "/headphones/13/headphones.v13.f6931%5Bnoarch%5D.spk",
                "arch": "apollolake",
                "build": "86009",
                "response_status": 200,
                "timestamp": "2026-06-15T00:00:00+0000",
            }
        )
        assert url_path == "headphones/13/headphones.v13.f6931[noarch].spk"
        assert noarch is True
        assert target_fw is None

    def test_no_timestamp_falls_back_to_today(self):
        url_path, arch_code, fw, rd, target_fw, noarch = parse_download(
            {
                "url": "/pkg/1/pkg.v1.f42661%5Barch%5D.spk",
                "arch": "arch",
                "build": "100",
                "response_status": 200,
            }
        )
        assert rd == date.today()

    def test_invalid_firmware_build_returns_none(self):
        url_path, arch_code, fw, rd, target_fw, noarch = parse_download(
            {
                "url": "/pkg/1/pkg.v1.f42661%5Barch%5D.spk",
                "arch": "arch",
                "build": "invalid",
                "response_status": 200,
            }
        )
        assert fw is None

    def test_evansport_single_arch(self):
        url_path, arch_code, fw, rd, target_fw, noarch = parse_download(
            {
                "url": "/navidrome/8/navidrome.v8.f42661%5Bevansport%5D.spk",
                "arch": "evansport",
                "build": "86009",
                "response_status": 200,
                "timestamp": "2026-06-14T10:53:08+0000",
            }
        )
        assert target_fw == 42661
        assert noarch is False
        assert url_path == "navidrome/8/navidrome.v8.f42661[evansport].spk"
