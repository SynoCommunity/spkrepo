# -*- coding: utf-8 -*-
import io
import os
from unittest.mock import MagicMock, patch

from flask import current_app

from spkrepo.ext import cache, db
from spkrepo.models import Build
from spkrepo.tests.common import (
    Architecture,
    BaseTestCase,
    BuildFactory,
    create_info,
    create_spk,
)
from spkrepo.views.tasks import resync_build_file, resync_build_metadata


def _build_stub(build_id, path=None):
    """Return a minimal Build-like object for testing skipped paths."""
    stub = MagicMock(spec=Build)
    stub.id = build_id
    stub.path = path
    return stub


class ResyncBuildMetadataTaskTestCase(BaseTestCase):
    """Unit tests for the resync_build_metadata Celery task."""

    def test_success_restores_metadata_and_recalculates_md5(self):
        build = BuildFactory()
        db.session.commit()

        original_display = build.version.displaynames["enu"].displayname
        original_md5 = build.calculate_md5()

        # Corrupt both a version-level and build-level field
        build.version.displaynames["enu"].displayname = "Corrupted"
        build.md5 = None
        db.session.commit()

        result = resync_build_metadata(build.id, str(build))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["build_id"], build.id)
        self.assertEqual(result["label"], str(build))

        db.session.expire_all()
        refreshed = db.session.get(Build, build.id)
        self.assertEqual(
            refreshed.version.displaynames["enu"].displayname, original_display
        )
        self.assertEqual(refreshed.md5, original_md5)

    def test_skipped_when_build_not_found(self):
        result = resync_build_metadata(999999, "nonexistent")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["build_id"], 999999)

    def test_skipped_when_build_has_no_path(self):
        """Task must return skipped when build.path is None without hitting
        the DB hooks."""
        stub = _build_stub(build_id=1, path=None)
        with patch("spkrepo.views.tasks.db.session.get", return_value=stub):
            result = resync_build_metadata(1, "stub")
        self.assertEqual(result["status"], "skipped")

    def test_error_on_metadata_mismatch_between_siblings(self):
        build1 = BuildFactory(architectures=[Architecture.find("88f628x")])
        build2 = BuildFactory(
            version=build1.version,
            architectures=[Architecture.find("cedarview")],
        )
        db.session.commit()

        # Write a mismatched displayname into build2's SPK on disk
        existing_displayname = build1.version.displaynames["enu"].displayname
        info2 = create_info(build2)
        info2["displayname"] = existing_displayname + " MODIFIED"
        info2["displayname_enu"] = existing_displayname + " MODIFIED"
        spk2_path = os.path.join(current_app.config["DATA_PATH"], build2.path)
        spk2_stream = create_spk(build2, info=info2)
        with open(spk2_path, "wb") as f:
            f.write(spk2_stream.read())

        result = resync_build_metadata(build1.id, str(build1))

        self.assertEqual(result["status"], "error")
        self.assertIn("mismatch", result["error"].lower())
        # DB must be unchanged — rollback must have fired
        db.session.expire_all()
        self.assertEqual(
            db.session.get(Build, build1.id).version.displaynames["enu"].displayname,
            existing_displayname,
        )

    def test_error_on_missing_spk_file(self):
        build = BuildFactory()
        db.session.commit()

        # Delete the file so the task hits a real FileNotFoundError on open
        spk_path = os.path.join(current_app.config["DATA_PATH"], build.path)
        os.remove(spk_path)

        result = resync_build_metadata(build.id, str(build))

        self.assertEqual(result["status"], "error")
        self.assertIn("build_id", result)

    def test_does_not_retry_on_value_error(self):
        """ValueError (e.g. metadata mismatch) must return error, never retry."""
        build = BuildFactory()
        db.session.commit()

        with patch(
            "spkrepo.views.tasks.extract_version_metadata",
            side_effect=ValueError("bad data"),
        ):
            result = resync_build_metadata(build.id, str(build))

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["error"], "bad data")

    def test_invalidates_cache_on_success(self):
        build = BuildFactory()
        db.session.commit()
        cache.set("packages_versions", "stale")
        result = resync_build_metadata(build.id, str(build))

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(cache.get("packages_versions"))

    def test_cache_not_invalidated_on_error(self):
        build = BuildFactory()
        db.session.commit()
        cache.set("packages_versions", "stale")
        with patch(
            "spkrepo.views.tasks.extract_version_metadata",
            side_effect=ValueError("bad data"),
        ):
            resync_build_metadata(build.id, str(build))

        # Cache must be untouched — the commit never ran
        self.assertEqual(cache.get("packages_versions"), "stale")

    def test_each_sibling_spk_opened_exactly_once(self):
        """Verify O(n) sibling reads: 3 builds → 3 SPK opens, no duplicates."""
        build1 = BuildFactory(architectures=[Architecture.find("88f628x")])
        # These siblings exist to populate version.builds via the DB relationship;
        # the task accesses them through build1.version.builds, not local variables
        BuildFactory(
            version=build1.version,
            architectures=[Architecture.find("cedarview")],
        )
        BuildFactory(
            version=build1.version,
            architectures=[Architecture.find("qoriq")],
        )
        db.session.commit()
        self.assertEqual(len(build1.version.builds), 3)

        opened_paths = []
        original_open = io.open

        def counting_open(path, *args, **kwargs):
            opened_paths.append(str(path))
            return original_open(path, *args, **kwargs)

        with patch("spkrepo.views.tasks.io.open", side_effect=counting_open):
            result = resync_build_metadata(build1.id, str(build1))

        self.assertEqual(result["status"], "ok")
        spk_opens = [p for p in opened_paths if p.endswith(".spk")]
        # build1 (own) + 2 siblings = exactly 3 opens
        self.assertEqual(len(spk_opens), 3)
        # No path opened more than once
        self.assertEqual(len(spk_opens), len(set(spk_opens)))


class ResyncBuildFileTaskTestCase(BaseTestCase):
    """Unit tests for the resync_build_file Celery task."""

    def test_success_recalculates_md5_and_size(self):
        build = BuildFactory()
        db.session.commit()

        expected_md5 = build.calculate_md5()
        build.md5 = None
        build.size = None
        db.session.commit()

        result = resync_build_file(build.id, str(build))

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["build_id"], build.id)
        self.assertEqual(result["label"], str(build))

        db.session.expire_all()
        refreshed = db.session.get(Build, build.id)
        self.assertEqual(refreshed.md5, expected_md5)
        self.assertIsNotNone(refreshed.size)
        self.assertGreater(refreshed.size, 0)

    def test_skipped_when_build_not_found(self):
        result = resync_build_file(999999, "nonexistent")
        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["build_id"], 999999)

    def test_skipped_when_build_has_no_path(self):
        """Task must return skipped when build.path is None without hitting
        the DB hooks."""
        stub = _build_stub(build_id=1, path=None)
        with patch("spkrepo.views.tasks.db.session.get", return_value=stub):
            result = resync_build_file(1, "stub")
        self.assertEqual(result["status"], "skipped")

    def test_error_on_missing_spk_file(self):
        build = BuildFactory()
        db.session.commit()

        spk_path = os.path.join(current_app.config["DATA_PATH"], build.path)
        os.remove(spk_path)

        result = resync_build_file(build.id, str(build))
        self.assertEqual(result["status"], "error")

    def test_error_does_not_persist_partial_changes(self):
        """If calculate_size raises after calculate_md5 succeeds, neither
        change should be committed to the DB."""
        build = BuildFactory()
        db.session.commit()

        original_md5 = build.md5

        # Use ValueError so it is caught without triggering the retry path
        with patch.object(Build, "calculate_size", side_effect=ValueError("bad size")):
            result = resync_build_file(build.id, str(build))

        self.assertEqual(result["status"], "error")
        self.assertIn("bad size", result["error"])
        db.session.expire_all()
        # md5 must not have been committed despite calculate_md5 succeeding
        self.assertEqual(db.session.get(Build, build.id).md5, original_md5)

    def test_invalidates_cache_on_success(self):
        build = BuildFactory()
        db.session.commit()
        cache.set("packages_versions", "stale")
        result = resync_build_file(build.id, str(build))

        self.assertEqual(result["status"], "ok")
        self.assertIsNone(cache.get("packages_versions"))

    def test_cache_not_invalidated_on_error(self):
        build = BuildFactory()
        db.session.commit()
        cache.set("packages_versions", "stale")
        # Use ValueError so it is caught without triggering the retry path
        with patch.object(Build, "calculate_size", side_effect=ValueError("bad size")):
            resync_build_file(build.id, str(build))

        self.assertEqual(cache.get("packages_versions"), "stale")
