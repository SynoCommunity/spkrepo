# -*- coding: utf-8 -*-
"""Integration test for the ingest_logs pipeline.

Mocks only the S3 boundary; exercises real JSON parsing, domain
aggregation, DB upsert, and object deletion as one flow.
"""
import gzip
import io
import json
from unittest.mock import patch

from spkrepo.ext import db
from spkrepo.models import Architecture, DownloadStat, Firmware
from spkrepo.tests.common import BaseTestCase, BuildFactory


class _FakeBody:
    """Minimal S3 body with the stream surface the task uses.

    Backed by BytesIO so gzip.open() can seek/read it; iter_lines() serves
    the uncompressed path.
    """

    def __init__(self, raw: bytes):
        self._raw = raw
        self._bio = io.BytesIO(raw)

    def iter_lines(self):
        return iter(self._raw.splitlines())

    def read(self, size=-1):
        return self._bio.read(size)

    def seek(self, *args):
        return self._bio.seek(*args)

    def tell(self):
        return self._bio.tell()


class _FakeS3:
    def __init__(self, objects, list_error=None, get_error_keys=()):
        self._objects = objects  # key -> bytes
        self._list_error = list_error
        self._get_error_keys = set(get_error_keys)
        self.deleted = []

    def list_objects_v2(self, **_kwargs):
        if self._list_error is not None:
            raise self._list_error
        return {"Contents": [{"Key": k} for k in self._objects]}

    def get_object(self, Bucket, Key):  # noqa: N803 (boto3 kwarg names)
        if Key in self._get_error_keys:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "NoSuchKey"}}, "GetObject")
        return {"Body": _FakeBody(self._objects[Key])}

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append(Key)


def _record(url, **overrides):
    record = {
        "url": url,
        "arch": "88f6281",
        "build": "1594",
        "response_status": 200,
        "timestamp": "2026-06-14T10:53:08",
    }
    record.update(overrides)
    return record


class IngestLogsTestCase(BaseTestCase):
    def _invoke(self, fake_s3):
        with patch("boto3.client", return_value=fake_s3):
            runner = self.app.test_cli_runner()
            return runner.invoke(args=["spkrepo", "ingest_logs"])

    def test_ingests_catalog_download_and_deletes_object(self):
        build = BuildFactory(
            active=True,
            architectures=[Architecture.find("88f628x")],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()

        body = json.dumps(_record("/" + build.path)).encode() + b"\n"
        fake = _FakeS3({"logs/a.jsonl": body})

        result = self._invoke(fake)

        self.assertEqual(result.exit_code, 0, result.output)
        rows = db.session.execute(db.select(DownloadStat)).scalars().all()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].count, 1)
        self.assertEqual(rows[0].build_id, build.id)
        self.assertEqual(rows[0].package_id, build.version.package_id)
        self.assertEqual(fake.deleted, ["logs/a.jsonl"])

    def test_reingest_accumulates_count(self):
        """Upsert path: ingesting the same download twice adds to the count."""
        build = BuildFactory(
            active=True,
            architectures=[Architecture.find("88f628x")],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()

        body = json.dumps(_record("/" + build.path)).encode() + b"\n"
        fake = _FakeS3({"logs/a.jsonl": body})

        self._invoke(fake)
        self._invoke(fake)

        row = db.session.execute(db.select(DownloadStat)).scalars().one()
        self.assertEqual(row.count, 2)

    def test_manual_download_has_no_device_dimensions(self):
        build = BuildFactory(
            active=True,
            architectures=[Architecture.find("88f628x")],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()

        body = json.dumps(_record("/" + build.path, arch="", build="")).encode()
        fake = _FakeS3({"logs/b.jsonl": body})

        result = self._invoke(fake)

        self.assertEqual(result.exit_code, 0, result.output)
        row = db.session.execute(db.select(DownloadStat)).scalars().one()
        self.assertEqual(row.download_source, "manual")
        self.assertIsNone(row.architecture_id)
        self.assertIsNone(row.firmware_build)

    def test_gzip_log_is_supported(self):
        build = BuildFactory(
            active=True,
            architectures=[Architecture.find("88f628x")],
            firmware_min=Firmware.find(1594),
        )
        db.session.commit()

        body = gzip.compress(json.dumps(_record("/" + build.path)).encode() + b"\n")
        fake = _FakeS3({"logs/c.jsonl.gz": body})

        result = self._invoke(fake)

        self.assertEqual(result.exit_code, 0, result.output)
        row = db.session.execute(db.select(DownloadStat)).scalars().one()
        self.assertEqual(row.count, 1)

    def test_unknown_build_path_is_skipped(self):
        body = json.dumps(_record("/nope/1/missing.spk")).encode()
        fake = _FakeS3({"logs/d.jsonl": body})

        result = self._invoke(fake)

        self.assertEqual(result.exit_code, 0, result.output)
        rows = db.session.execute(db.select(DownloadStat)).scalars().all()
        self.assertEqual(rows, [])
        # processed key is still deleted after a successful read
        self.assertEqual(fake.deleted, ["logs/d.jsonl"])

    def test_empty_bucket_is_noop(self):
        result = self._invoke(_FakeS3({}))
        self.assertEqual(result.exit_code, 0, result.output)

    def test_unreadable_object_is_skipped(self):
        body = json.dumps(_record("/p/1/a.spk")).encode()
        fake = _FakeS3({"logs/e.jsonl": body}, get_error_keys={"logs/e.jsonl"})

        result = self._invoke(fake)

        self.assertEqual(result.exit_code, 0, result.output)
        rows = db.session.execute(db.select(DownloadStat)).scalars().all()
        self.assertEqual(rows, [])
