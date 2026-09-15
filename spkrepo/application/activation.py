# -*- coding: utf-8 -*-
"""Activation use-case: decide which builds activate and queue for upload.

Pure planner shared by the version and build admin activate actions (which
previously duplicated this branch logic inline). Transports resolve each
build's effective ``signed`` flag (including signature recovery), apply the
plan (set ``active``, queue uploads, invalidate caches), and map the result
to flashes/HTTP.
"""


def plan_activation(builds, storage_configured):
    """Split builds into activate / reject / upload queues.

    :param builds: iterable of ``{"id":…, "label":…, "signed": bool,
        "storage": "local"|"remote"}`` snapshots with effective signed state
    :param storage_configured: whether Object Storage uploads are enabled
    :returns: ``{"to_activate": […], "not_signed": […], "to_upload": […]}``
        where ``to_upload`` ⊆ ``to_activate`` (local + storage enabled)
    """
    to_activate = []
    not_signed = []
    for build in builds:
        if build.get("signed"):
            to_activate.append(build)
        else:
            not_signed.append(build)
    to_upload = [
        b for b in to_activate
        if storage_configured and b.get("storage", "local") == "local"
    ]
    return {
        "to_activate": to_activate,
        "not_signed": not_signed,
        "to_upload": to_upload,
    }
