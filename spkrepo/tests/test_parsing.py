# -*- coding: utf-8 -*-
"""Thin-adapter wiring probes for cli.parse helpers.

Branch tables live in test_domain.py (pure domain fns); these two prove
the cli.py wrappers delegate without re-pinning the matrix.
"""

from spkrepo.cli import is_countable_download, parse_download


class TestCliWiring:
    def test_countable_passthrough(self):
        assert (
            is_countable_download({"url": "/pkg/1/pkg.v1.spk", "response_status": 200})
            is True
        )
        assert (
            is_countable_download(
                {"url": "/some/other/file.txt", "response_status": 200}
            )
            is False
        )

    def test_parse_passthrough(self):
        url_path, arch_code, fw, _, target_fw, noarch = parse_download(
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
        assert target_fw == 42661
        assert noarch is False
