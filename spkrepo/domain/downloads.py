# -*- coding: utf-8 -*-
"""Pure download-log domain: countable check, parse, classify, aggregate.

No S3/DB/date-today side effects except an explicit fallback parameter so
units can inject a fixed date.
"""

import urllib.parse
from collections import defaultdict
from datetime import date, datetime


def is_full_range(range_header: str) -> bool:
    """True for '' or 'bytes=0-...' (countable resumed-download start).

    Mid-range resumes (``bytes=N-`` with N > 0) must not double-count the
    same download.
    """
    range_header = range_header or ""
    return range_header == "" or range_header.startswith("bytes=0-")


def is_countable_download(record: dict) -> bool:
    """True if a CDN log record represents a countable download."""
    url = record.get("url", "")
    path = url.split("?")[0]
    if not path.endswith(".spk"):
        return False
    status = record.get("response_status")
    if status == 200:
        return True
    if status == 206:
        return is_full_range(record.get("range", ""))
    return False


def parse_download(
    record: dict, today: date | None = None
) -> tuple[str, str | None, int | None, date, int | None, bool]:
    """Parse a CDN record -> (path, arch, fw_build, date, target_fw, noarch).

    Pure except the missing-timestamp fallback, which defaults to
    ``date.today()`` but accepts an injected ``today`` for tests.
    """
    from .shared_kernel import parse_filename_target

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
        record_date = today or date.today()

    filename = path.rsplit("/", 1)[-1] if "/" in path else path
    target_firmware_build, target_noarch = parse_filename_target(filename)
    return (
        path.lstrip("/"),
        arch_code,
        firmware_build,
        record_date,
        target_firmware_build,
        target_noarch,
    )


def classify_source(arch_code: str | None, firmware_build: int | None) -> str:
    """Catalog downloads carry both arch+build; otherwise manual."""
    if arch_code is None or firmware_build is None:
        return "manual"
    return "catalog"


def aggregate_parsed(
    parsed: list[tuple],
) -> tuple[dict, dict, dict]:
    """Aggregate parsed rows -> (counts, target_noarchs, sources) keyed by
    agg-key tuples ``(package_id, architecture_id, firmware_build,
    target_firmware_build, date)`` whose ``package_id``/``build_id`` the
    adapter resolves (``cli.ingest_logs`` build cache).

    Pure counting step; DB build/package resolution stays in the adapter.
    Input rows: (agg_key_tuple, target_noarch_bool, source_str).
    """
    counts: dict = defaultdict(int)
    noarchs: dict = {}
    sources: dict = {}
    for agg_key, target_noarch, source in parsed:
        counts[agg_key] += 1
        noarchs[agg_key] = target_noarch
        sources[agg_key] = source
    return dict(counts), noarchs, sources


def build_upsert_rows(
    counts: dict,
    build_ids: dict,
    target_noarchs: dict,
    download_sources: dict,
) -> list[dict]:
    """Build DownloadStat upsert row dicts from aggregated counts."""
    rows = []
    for agg_key, count in counts.items():
        (
            package_id,
            architecture_id,
            firmware_build,
            target_firmware_build,
            record_date,
        ) = agg_key
        rows.append(
            {
                "package_id": package_id,
                "build_id": build_ids.get(agg_key),
                "architecture_id": architecture_id,
                "firmware_build": firmware_build,
                "target_firmware_build": target_firmware_build,
                "target_noarch": target_noarchs.get(agg_key, False),
                "download_source": download_sources.get(agg_key, "catalog"),
                "date": record_date,
                "count": count,
            }
        )
    return rows
