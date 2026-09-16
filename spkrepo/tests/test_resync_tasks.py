# -*- coding: utf-8 -*-
import io
import json
import os
from unittest.mock import MagicMock, patch

from flask import current_app

from spkrepo.adapters.spk_io import SPK
from spkrepo.ext import db
from spkrepo.models import Build
from spkrepo.tests.common import (
    Architecture,
    BaseTestCase,
    BuildFactory,
    create_info,
    create_spk,
)
from spkrepo.views.frontend import _packages_for_arch
from spkrepo.views.tasks import resync_build_file, resync_build_metadata

#: Arbitrary key used only to observe the memoized packages-list cache.
_PROBE_ARCH = "__probe__"


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

    def test_sibling_with_sidecar_is_compared_by_sidecar_metadata(self):
        """A sibling that only has a sidecar (no local SPK) must be compared
        via its sidecar metadata, not crash on missing attributes."""
        build1 = BuildFactory(architectures=[Architecture.find("88f628x")])
        build2 = BuildFactory(
            version=build1.version,
            architectures=[Architecture.find("cedarview")],
        )
        db.session.commit()

        # Sibling 2: sidecar only, no local .spk.
        spk2_path = os.path.join(current_app.config["DATA_PATH"], build2.path)
        os.remove(spk2_path)
        sidecar2_path = spk2_path + ".json"
        with create_spk(build2) as stream:
            spk2 = SPK(stream)
            sidecar2 = {
                "info": spk2.info,
                "derived": {
                    "install_wizard": False,
                    "upgrade_wizard": False,
                    "startable": True,
                    "license": spk2.license,
                },
            }
        with open(sidecar2_path, "w") as f:
            json.dump(sidecar2, f)

        result = resync_build_metadata(build1.id, str(build1))

        self.assertEqual(result["status"], "ok", result.get("error"))

    def test_value_error_returns_error_without_retry_or_cache_invalidation(self):
        """ValueError (e.g. metadata mismatch) must return error, never retry,
        and must leave the cached packages list untouched."""
        build = BuildFactory()
        db.session.commit()

        with patch(
            "spkrepo.views.frontend._latest_versions_query", return_value=[]
        ) as query:
            _packages_for_arch(_PROBE_ARCH)  # prime
            query.reset_mock()
            with patch(
                "spkrepo.views.tasks.extract_version_metadata",
                side_effect=ValueError("bad data"),
            ):
                result = resync_build_metadata(build.id, str(build))

            self.assertEqual(result["status"], "error")
            self.assertEqual(result["error"], "bad data")
            _packages_for_arch(_PROBE_ARCH)  # still cached
            self.assertEqual(query.call_count, 0)

    def test_invalidates_cache_on_success(self):
        build = BuildFactory()
        db.session.commit()

        with patch(
            "spkrepo.views.frontend._latest_versions_query", return_value=[]
        ) as query:
            _packages_for_arch(_PROBE_ARCH)  # prime
            query.reset_mock()
            result = resync_build_metadata(build.id, str(build))

            self.assertEqual(result["status"], "ok")
            _packages_for_arch(_PROBE_ARCH)  # invalidated -> recomputed
            self.assertEqual(query.call_count, 1)

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

        with patch(
            "spkrepo.views.frontend._latest_versions_query", return_value=[]
        ) as query:
            _packages_for_arch(_PROBE_ARCH)  # prime
            query.reset_mock()
            result = resync_build_file(build.id, str(build))

            self.assertEqual(result["status"], "ok")
            _packages_for_arch(_PROBE_ARCH)  # invalidated -> recomputed
            self.assertEqual(query.call_count, 1)

    def test_cache_not_invalidated_on_error(self):
        build = BuildFactory()
        db.session.commit()
        with patch(
            "spkrepo.views.frontend._latest_versions_query", return_value=[]
        ) as query:
            _packages_for_arch(_PROBE_ARCH)  # prime
            query.reset_mock()
            # Use ValueError so it is caught without triggering the retry path
            with patch.object(
                Build, "calculate_size", side_effect=ValueError("bad size")
            ):
                resync_build_file(build.id, str(build))

            _packages_for_arch(_PROBE_ARCH)  # still cached
            self.assertEqual(query.call_count, 0)


class SidecarRoundTripTestCase(BaseTestCase):
    """The sidecar written by upload_to_storage must be readable by
    resync_build_metadata (writer/reader cross-task contract)."""

    def test_upload_written_sidecar_is_applied_by_resync(self):
        from spkrepo.views.tasks import upload_to_storage

        build = BuildFactory(signed=True, active=True)
        db.session.commit()

        with patch("spkrepo.views.tasks.storage.upload", return_value=True):
            result = upload_to_storage(build.id, str(build))
        self.assertEqual(result["status"], "ok")

        db.session.expire_all()
        build = db.session.get(Build, build.id)
        self.assertEqual(build.storage, "remote")
        sidecar_path = os.path.join(
            current_app.config["DATA_PATH"], build.path + ".json"
        )
        self.assertTrue(os.path.exists(sidecar_path))

        # Corrupt a version field the sidecar carries, then resync.
        build.version.upstream_version = "CORRUPT"
        db.session.commit()

        result = resync_build_metadata(build.id, str(build))
        self.assertEqual(result["status"], "ok")
        db.session.expire_all()
        self.assertNotEqual(
            db.session.get(Build, build.id).version.upstream_version, "CORRUPT"
        )


class CeleryAppBindingTestCase(BaseTestCase):
    """Celery tasks must resolve the current app at call time.

    Tasks are defined once and their FlaskTask base is resolved lazily; if it
    closed over the create_app() app instead, the second and later apps in a
    process (i.e. every test after the first) would run tasks against a stale,
    dropped app context — surfacing as "no such table" in ordered runs.
    """

    def test_task_binds_to_current_app(self):
        from spkrepo.ext import celery

        self.assertIs(celery.spkrepo_app, self.app)

    def test_task_callable_without_explicit_context(self):
        # Calling a task directly (as tests and the worker do) must succeed
        # because FlaskTask pushes the bound app's context itself.
        build = BuildFactory()
        db.session.commit()
        result = resync_build_file(build.id, str(build))
        self.assertEqual(result["status"], "ok")
