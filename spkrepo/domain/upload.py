# -*- coding: utf-8 -*-
"""Pure upload/conflict domain. No DB/Flask/FS.

Adapters resolve ORM objects to these lightweight snapshots before calling.
"""

from .shared_kernel import validate_firmware_range  # noqa: F401 (re-export)


def detect_conflicts(
    existing: list[dict],
    candidate_archs: set[str],
    candidate_min: int,
    candidate_max: int | None,
) -> set[str]:
    """Return conflicting arch codes where fw ranges overlap.

    :param existing: [{'archs': set[str], 'min': int, 'max': int|None}] —
        None max means single-fw build (max == min).
    """
    cand_max = candidate_max if candidate_max is not None else candidate_min
    conflicts: set[str] = set()
    for build in existing:
        overlap = set(build.get("archs", set())) & set(candidate_archs)
        if not overlap:
            continue
        exist_min = build["min"]
        exist_max = build.get("max", exist_min)
        if exist_max is None:
            exist_max = exist_min
        if candidate_min > exist_max or cand_max < exist_min:
            continue
        conflicts |= set(overlap)
    return conflicts


def authorize_upload(
    roles: set[str], is_new_package: bool, is_maintainer: bool
) -> None:
    """Raise PermissionError if upload is not allowed (pure decision)."""
    if "package_admin" in roles:
        return
    if not is_new_package and is_maintainer:
        return
    raise PermissionError(
        "Insufficient permissions to create new packages"
        if is_new_package
        else "Insufficient permissions on this package"
    )


def firmware_range_valid(min_build: int, max_build: int | None) -> bool:
    """Non-raising variant for form-level checks."""
    if max_build is not None and max_build < min_build:
        return False
    return True
