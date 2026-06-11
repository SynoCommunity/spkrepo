# -*- coding: utf-8 -*-
import logging
import os

import boto3
import requests
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError
from flask import current_app

logger = logging.getLogger(__name__)


def storage_configured():
    """Return True if the packages Object Storage config keys are populated."""
    return all(
        [
            current_app.config["OBJECT_STORAGE_PACKAGES_ENDPOINT"],
            current_app.config["OBJECT_STORAGE_PACKAGES_BUCKET"],
            current_app.config["OBJECT_STORAGE_PACKAGES_ACCESS_KEY"],
            current_app.config["OBJECT_STORAGE_PACKAGES_SECRET_KEY"],
            current_app.config["OBJECT_STORAGE_PACKAGES_REGION"],
        ]
    )


def _client():
    """Return a boto3 S3 client for the packages bucket."""
    config = Config(
        request_checksum_calculation="when_required",
    )
    return boto3.client(
        "s3",
        config=config,
        endpoint_url=current_app.config["OBJECT_STORAGE_PACKAGES_ENDPOINT"],
        aws_access_key_id=current_app.config["OBJECT_STORAGE_PACKAGES_ACCESS_KEY"],
        aws_secret_access_key=current_app.config["OBJECT_STORAGE_PACKAGES_SECRET_KEY"],
        region_name=current_app.config["OBJECT_STORAGE_PACKAGES_REGION"],
    )


def upload(local_path, object_key):
    """Upload a local file to Object Storage. Returns True on success."""
    if not storage_configured():
        logger.warning("Object Storage not configured — upload skipped")
        return False
    try:
        s3 = _client()
        s3.upload_file(
            local_path,
            current_app.config["OBJECT_STORAGE_PACKAGES_BUCKET"],
            object_key,
        )
        logger.info("Uploaded %s to object storage", object_key)
        return True
    except (BotoCoreError, ClientError) as e:
        logger.error("Failed to upload %s: %s", object_key, e)
        return False


def download(object_key, local_path):
    """Download a file from Object Storage to a local path. Returns True on success."""
    if not storage_configured():
        logger.warning("Object Storage not configured — download skipped")
        return False
    try:
        s3 = _client()
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        s3.download_file(
            current_app.config["OBJECT_STORAGE_PACKAGES_BUCKET"],
            object_key,
            local_path,
        )
        logger.info("Downloaded %s to %s", object_key, local_path)
        return True
    except (BotoCoreError, ClientError) as e:
        logger.error("Failed to download %s: %s", object_key, e)
        return False


def delete(object_key):
    """Delete a file from Object Storage. Returns True on success."""
    if not storage_configured():
        logger.warning("Object Storage not configured — delete skipped")
        return False
    try:
        s3 = _client()
        s3.delete_object(
            Bucket=current_app.config["OBJECT_STORAGE_PACKAGES_BUCKET"],
            Key=object_key,
        )
        logger.info("Deleted %s from object storage", object_key)
        return True
    except (BotoCoreError, ClientError) as e:
        logger.error("Failed to delete %s: %s", object_key, e)
        return False


def purge_cdn(url_path):
    """Issue a CDN purge for the given URL path. Logs and skips if not configured."""
    token = current_app.config.get("CDN_PURGE_TOKEN")
    host = current_app.config.get("PACKAGES_CDN_HOST")
    if not token or not host:
        logger.info("CDN purge skipped (not configured): %s", url_path)
        return
    url = f"https://{host}{url_path}"
    try:
        requests.request("PURGE", url, headers={"Fastly-Key": token}, timeout=10)
        logger.info("CDN purge issued: %s", url)
    except requests.RequestException as e:
        logger.warning("CDN purge failed for %s: %s", url, e)
