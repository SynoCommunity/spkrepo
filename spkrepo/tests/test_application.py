# -*- coding: utf-8 -*-
"""Cheap use-case units for spkrepo.application — no app, DB, or network."""
from spkrepo.application.activation import plan_activation


class TestPlanActivation:
    def test_empty(self):
        assert plan_activation([], True) == {
            "to_activate": [],
            "not_signed": [],
            "to_upload": [],
        }

    def test_signed_local_queues_upload(self):
        b = {"id": 1, "label": "b", "signed": True, "storage": "local"}
        plan = plan_activation([b], True)
        assert plan["to_activate"] == [b]
        assert plan["not_signed"] == []
        assert plan["to_upload"] == [b]

    def test_unsigned_rejected(self):
        b = {"id": 1, "label": "b", "signed": False, "storage": "local"}
        plan = plan_activation([b], True)
        assert plan["to_activate"] == []
        assert plan["not_signed"] == [b]
        assert plan["to_upload"] == []

    def test_remote_skips_upload(self):
        b = {"id": 1, "label": "b", "signed": True, "storage": "remote"}
        assert plan_activation([b], True)["to_upload"] == []

    def test_storage_disabled_skips_upload(self):
        b = {"id": 1, "label": "b", "signed": True, "storage": "local"}
        plan = plan_activation([b], False)
        assert plan["to_activate"] == [b]
        assert plan["to_upload"] == []

    def test_mixed_batch(self):
        ok = {"id": 1, "label": "a", "signed": True, "storage": "local"}
        remote = {"id": 2, "label": "b", "signed": True, "storage": "remote"}
        bad = {"id": 3, "label": "c", "signed": False, "storage": "local"}
        plan = plan_activation([ok, remote, bad], True)
        assert plan["to_activate"] == [ok, remote]
        assert plan["not_signed"] == [bad]
        assert plan["to_upload"] == [ok]

    def test_missing_keys_use_defaults(self):
        # Missing storage -> "local" (uploadable); missing signed -> rejected.
        bare = {"id": 1, "label": "a"}
        assert plan_activation([bare], True)["not_signed"] == [bare]
        no_storage = {"id": 2, "label": "b", "signed": True}
        plan = plan_activation([no_storage], True)
        assert plan["to_activate"] == [no_storage]
        assert plan["to_upload"] == [no_storage]
