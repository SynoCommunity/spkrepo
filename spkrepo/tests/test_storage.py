# -*- coding: utf-8 -*-
"""Unit tests for the S3 storage adapter (boto3/requests mocked)."""

import os
from unittest.mock import MagicMock, patch

import requests
from botocore.exceptions import ClientError

from spkrepo import storage
from spkrepo.tests.common import BaseTestCase

PACKAGES_CONFIG = {
    "OBJECT_STORAGE_PACKAGES_ENDPOINT": "https://s3.example.com",
    "OBJECT_STORAGE_PACKAGES_BUCKET": "bucket",
    "OBJECT_STORAGE_PACKAGES_ACCESS_KEY": "key",
    "OBJECT_STORAGE_PACKAGES_SECRET_KEY": "secret",
    "OBJECT_STORAGE_PACKAGES_REGION": "us-east",
}


def _client_error(operation):
    return ClientError({"Error": {"Code": "Boom"}}, operation)


class StorageConfiguredTestCase(BaseTestCase):
    def test_false_when_unset(self):
        self.assertFalse(storage.storage_configured())

    def test_true_when_all_set(self):
        self.app.config.update(PACKAGES_CONFIG)
        self.assertTrue(storage.storage_configured())


class StorageOperationsTestCase(BaseTestCase):
    def setUp(self):
        super().setUp()
        self.app.config.update(PACKAGES_CONFIG)

    def test_upload_true_on_success(self):
        client = MagicMock()
        with patch("spkrepo.storage.boto3.client", return_value=client):
            self.assertTrue(storage.upload("/tmp/a.spk", "a.spk"))
        client.upload_file.assert_called_once_with("/tmp/a.spk", "bucket", "a.spk")

    def test_upload_false_on_error(self):
        client = MagicMock()
        client.upload_file.side_effect = _client_error("PutObject")
        with patch("spkrepo.storage.boto3.client", return_value=client):
            self.assertFalse(storage.upload("/tmp/a.spk", "a.spk"))

    def test_download_true_creates_parent(self):
        client = MagicMock()
        target = os.path.join(self.app.config["DATA_PATH"], "sub", "a.spk")
        with patch("spkrepo.storage.boto3.client", return_value=client):
            self.assertTrue(storage.download("a.spk", target))
        self.assertTrue(os.path.isdir(os.path.dirname(target)))
        client.download_file.assert_called_once_with("bucket", "a.spk", target)

    def test_download_false_on_error(self):
        client = MagicMock()
        client.download_file.side_effect = _client_error("GetObject")
        with patch("spkrepo.storage.boto3.client", return_value=client):
            self.assertFalse(storage.download("a.spk", "/tmp/nope/a.spk"))

    def test_delete_true_on_success(self):
        client = MagicMock()
        with patch("spkrepo.storage.boto3.client", return_value=client):
            self.assertTrue(storage.delete("a.spk"))
        client.delete_object.assert_called_once_with(Bucket="bucket", Key="a.spk")

    def test_delete_false_on_error(self):
        client = MagicMock()
        client.delete_object.side_effect = _client_error("DeleteObject")
        with patch("spkrepo.storage.boto3.client", return_value=client):
            self.assertFalse(storage.delete("a.spk"))


class StorageUnconfiguredTestCase(BaseTestCase):
    def test_operations_skip_without_calling_boto3(self):
        with patch("spkrepo.storage.boto3.client") as client:
            self.assertFalse(storage.upload("/tmp/a.spk", "a.spk"))
            self.assertFalse(storage.download("a.spk", "/tmp/a.spk"))
            self.assertFalse(storage.delete("a.spk"))
        client.assert_not_called()


class CdnPurgeTestCase(BaseTestCase):
    def test_skipped_when_unconfigured(self):
        with patch("spkrepo.storage.requests.request") as request:
            storage.purge_cdn("/pkg/1/a.spk")
        request.assert_not_called()

    def test_issues_purge(self):
        self.app.config["CDN_PURGE_TOKEN"] = "token"
        self.app.config["PACKAGES_CDN_HOST"] = "cdn.example.com"
        with patch("spkrepo.storage.requests.request") as request:
            storage.purge_cdn("/pkg/1/a.spk")
        request.assert_called_once_with(
            "PURGE",
            "https://cdn.example.com/pkg/1/a.spk",
            headers={"Fastly-Key": "token"},
            timeout=10,
        )

    def test_request_errors_are_swallowed(self):
        self.app.config["CDN_PURGE_TOKEN"] = "token"
        self.app.config["PACKAGES_CDN_HOST"] = "cdn.example.com"
        with patch(
            "spkrepo.storage.requests.request",
            side_effect=requests.RequestException("boom"),
        ):
            storage.purge_cdn("/pkg/1/a.spk")
