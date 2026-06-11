# -*- coding: utf-8 -*-
import hashlib
import io
import json
import os
import tarfile
from datetime import datetime, timezone

from flask import current_app

from .. import storage
from ..ext import cache, celery, db
from ..models import Build
from ..utils import (
    SPK,
    apply_info_from_spk,
    apply_sidecar_to_db,
    extract_version_metadata,
)
from .nas import clear_catalog_cache


@celery.task(bind=True, max_retries=3, default_retry_delay=10, queue="ops")
def resync_build_metadata(self, build_id, build_label):
    """Re-read build metadata from sidecar or SPK and reapply to DB.

    If the build has a sidecar (Object Storage), reads metadata from the
    sidecar. Otherwise parses the local .spk file and checks consistency
    against siblings.
    """
    build = db.session.get(Build, build_id)
    if not build or not build.path:
        return {"status": "skipped", "build_id": build_id, "label": build_label}

    try:
        data_path = current_app.config["DATA_PATH"]
        sidecar_path = os.path.join(data_path, build.path + ".json")

        if os.path.exists(sidecar_path):
            with io.open(sidecar_path, "r", encoding="utf-8") as f:
                sidecar = json.load(f)
            apply_sidecar_to_db(db.session, build, sidecar)
            db.session.commit()
            cache.delete("packages_versions")
            clear_catalog_cache()
            return {"status": "ok", "build_id": build_id, "label": build_label}

        # No sidecar — read from local .spk
        file_path = os.path.join(data_path, build.path)
        with io.open(file_path, "rb") as stream:
            spk = SPK(stream)
            incoming_meta = extract_version_metadata(spk)

            for sibling in build.version.builds:
                if sibling.id == build.id or not sibling.path:
                    continue
                sibling_path = os.path.join(data_path, sibling.path)
                with io.open(sibling_path, "rb") as s2:
                    sibling_meta = extract_version_metadata(SPK(s2))
                if sibling_meta != incoming_meta:
                    raise ValueError(
                        "Version-level metadata mismatch between "
                        f"{os.path.basename(build.path)} and "
                        f"{os.path.basename(sibling.path)} — resync aborted."
                    )

            md5 = spk.calculate_md5()
            apply_info_from_spk(db.session, build, spk, md5)
            db.session.commit()
            cache.delete("packages_versions")
            clear_catalog_cache()

        return {"status": "ok", "build_id": build_id, "label": build_label}

    except (ValueError, FileNotFoundError) as exc:
        db.session.rollback()
        return {
            "status": "error",
            "build_id": build_id,
            "label": build_label,
            "error": str(exc),
        }

    except Exception as exc:
        db.session.rollback()
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "status": "error",
                "build_id": build_id,
                "label": build_label,
                "error": str(exc),
            }


@celery.task(bind=True, max_retries=3, default_retry_delay=10, queue="ops")
def resync_build_file(self, build_id, build_label):
    """Recalculate md5 and size from sidecar or local file."""
    build = db.session.get(Build, build_id)
    if not build or not build.path:
        return {"status": "skipped", "build_id": build_id, "label": build_label}

    try:
        data_path = current_app.config["DATA_PATH"]
        sidecar_path = os.path.join(data_path, build.path + ".json")

        if os.path.exists(sidecar_path):
            with io.open(sidecar_path, "r", encoding="utf-8") as f:
                sidecar = json.load(f)
            build.md5 = sidecar["calculated"]["md5"]
            build.size = sidecar["calculated"]["size"]
        else:
            build.md5 = build.calculate_md5()
            build.size = build.calculate_size()

        db.session.commit()
        cache.delete("packages_versions")
        clear_catalog_cache()
        return {"status": "ok", "build_id": build_id, "label": build_label}

    except (ValueError, FileNotFoundError) as exc:
        db.session.rollback()
        return {
            "status": "error",
            "build_id": build_id,
            "label": build_label,
            "error": str(exc),
        }

    except Exception as exc:
        db.session.rollback()
        try:
            raise self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            return {
                "status": "error",
                "build_id": build_id,
                "label": build_label,
                "error": str(exc),
            }


@celery.task(bind=True, max_retries=3, default_retry_delay=10, queue="ops")
def upload_to_storage(self, build_id, build_label):
    """Upload a signed, active build from local disk to Object Storage."""
    build = db.session.get(Build, build_id)
    if not build or not build.path:
        return {
            "status": "skipped",
            "type": "upload",
            "build_id": build_id,
            "label": build_label,
        }

    data_path = current_app.config["DATA_PATH"]
    spk_path = os.path.join(data_path, build.path)
    object_key = build.path
    sidecar_path = spk_path + ".json"

    if not os.path.exists(spk_path):
        return {
            "status": "error",
            "type": "upload",
            "build_id": build_id,
            "label": build_label,
            "error": "File not found on disk",
        }

    if not build.signed:
        return {
            "status": "error",
            "type": "upload",
            "build_id": build_id,
            "label": build_label,
            "error": "Build is not signed",
        }

    if os.path.exists(sidecar_path):
        return {
            "status": "skipped",
            "type": "upload",
            "build_id": build_id,
            "label": build_label,
            "error": "Already uploaded (sidecar exists)",
        }

    try:
        info = {}
        install_wizard = False
        upgrade_wizard = False
        license_text = None

        with tarfile.open(spk_path, "r:") as archive:
            names = archive.getnames()
            if "INFO" in names:
                info_stream = archive.extractfile("INFO")
                if info_stream:
                    raw = info_stream.read().decode("utf-8").strip()
                    for line in raw.split("\n"):
                        if "=" not in line:
                            continue
                        eq = line.index("=")
                        key = line[:eq].strip()
                        val = line[eq + 1 :].strip().strip('"')
                        info[key] = val
            if "WIZARD_UIFILES/install_uifile" in names:
                install_wizard = True
            if "WIZARD_UIFILES/upgrade_uifile" in names:
                upgrade_wizard = True
            if "LICENSE" in names:
                lic_stream = archive.extractfile("LICENSE")
                if lic_stream:
                    license_text = (
                        lic_stream.read().decode("utf-8", errors="replace").strip()
                    )

        md5_hash = hashlib.md5()
        sha256_hash = hashlib.sha256()
        file_size = 0
        with io.open(spk_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                md5_hash.update(chunk)
                sha256_hash.update(chunk)
                file_size += len(chunk)

        sidecar = {
            "info": info,
            "derived": {
                "install_wizard": install_wizard,
                "upgrade_wizard": upgrade_wizard,
                "startable": (
                    info.get("startable", "yes") != "no"
                    and info.get("ctl_stop", "yes") != "no"
                ),
                "license": license_text,
            },
            "calculated": {
                "md5": md5_hash.hexdigest(),
                "sha256": sha256_hash.hexdigest(),
                "size": file_size,
                "uploaded_at": datetime.now(timezone.utc).isoformat(),
                "object_storage_key": object_key,
                "sidecar_version": 1,
            },
        }

        tmp_sidecar = sidecar_path + ".tmp"
        with io.open(tmp_sidecar, "w", encoding="utf-8") as f:
            json.dump(sidecar, f, indent=2, ensure_ascii=False)
        os.rename(tmp_sidecar, sidecar_path)

        if not storage.upload(spk_path, object_key):
            os.remove(sidecar_path)
            return {
                "status": "error",
                "type": "upload",
                "build_id": build_id,
                "label": build_label,
                "error": "Upload to Object Storage failed",
            }

        build.storage = "remote"
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        if os.path.exists(sidecar_path):
            os.remove(sidecar_path)
        return {
            "status": "error",
            "type": "upload",
            "build_id": build_id,
            "label": build_label,
            "error": str(exc),
        }

    try:
        os.remove(spk_path)
    except OSError:
        pass

    storage.purge_cdn("/" + object_key)
    return {
        "status": "ok",
        "type": "upload",
        "build_id": build_id,
        "label": build_label,
    }


@celery.task(bind=True, max_retries=3, default_retry_delay=10, queue="ops")
def rehome_from_storage(self, build_id, build_label):
    """Download a build from Object Storage back to local disk for editing."""
    build = db.session.get(Build, build_id)
    if not build or not build.path:
        return {
            "status": "skipped",
            "type": "rehome",
            "build_id": build_id,
            "label": build_label,
        }

    data_path = current_app.config["DATA_PATH"]
    local_path = os.path.join(data_path, build.path)

    if not storage.download(build.path, local_path):
        return {
            "status": "error",
            "type": "rehome",
            "build_id": build_id,
            "label": build_label,
            "error": "Download from Object Storage failed",
        }

    sidecar_path = local_path + ".json"
    if os.path.exists(sidecar_path):
        os.remove(sidecar_path)

    storage.delete(build.path)
    storage.purge_cdn("/" + build.path)

    build.storage = "local"
    db.session.commit()
    cache.delete("packages_versions")
    clear_catalog_cache()
    return {
        "status": "ok",
        "type": "rehome",
        "build_id": build_id,
        "label": build_label,
    }
