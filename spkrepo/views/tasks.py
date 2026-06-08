# -*- coding: utf-8 -*-
import io
import os

from flask import current_app

from ..ext import cache, celery, db
from ..models import Build
from ..utils import SPK, apply_info_from_spk, extract_version_metadata


@celery.task(bind=True, max_retries=3, default_retry_delay=10, queue="resync")
def resync_build_metadata(self, build_id, build_label):
    """Re-read the SPK file for a build and reapply its metadata to the DB.

    Sibling SPK files are read once each and compared against the target
    build's metadata, avoiding the O(n²) I/O of the original synchronous
    implementation.
    """
    build = db.session.get(Build, build_id)
    if not build or not build.path:
        return {"status": "skipped", "build_id": build_id, "label": build_label}

    try:
        data_path = current_app.config["DATA_PATH"]
        file_path = os.path.join(data_path, build.path)

        with io.open(file_path, "rb") as stream:
            spk = SPK(stream)
            incoming_meta = extract_version_metadata(spk)

            # Read each sibling once and compare — O(n) instead of O(n²)
            for sibling in build.version.builds:
                if sibling.id == build.id or not sibling.path:
                    continue
                sibling_path = os.path.join(data_path, sibling.path)
                with io.open(sibling_path, "rb") as s2:
                    sibling_meta = extract_version_metadata(SPK(s2))
                if sibling_meta != incoming_meta:
                    raise ValueError(
                        f"Version-level metadata mismatch between "
                        f"{os.path.basename(build.path)} and "
                        f"{os.path.basename(sibling.path)} — resync aborted."
                    )

            md5 = spk.calculate_md5()
            apply_info_from_spk(db.session, build, spk, md5)
            db.session.commit()
            cache.delete("packages_versions")

        return {"status": "ok", "build_id": build_id, "label": build_label}

    except (ValueError, FileNotFoundError) as exc:
        # Data errors (mismatch, missing file, etc.) — don't retry
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


@celery.task(bind=True, max_retries=3, default_retry_delay=10, queue="resync")
def resync_build_file(self, build_id, build_label):
    """Recalculate md5 and size for a build from its file on disk."""
    build = db.session.get(Build, build_id)
    if not build or not build.path:
        return {"status": "skipped", "build_id": build_id, "label": build_label}

    try:
        build.md5 = build.calculate_md5()
        build.size = build.calculate_size()
        db.session.commit()
        cache.delete("packages_versions")
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
