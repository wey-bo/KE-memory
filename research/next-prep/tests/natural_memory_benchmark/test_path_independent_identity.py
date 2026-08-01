"""Regressions for path-independent artifact identity.

The repair allows the workspace root to move. It must not make an artifact's
position *inside* the workspace irrelevant, so most of these tests are about what
still fails: same bytes at a different relative path, same relative path with
different bytes, an unlisted historical root, and traversal or symlink escapes.

The six cases named in the ruling are covered by
``test_different_workspace_root_same_relative_path_and_hash_passes``,
``test_same_basename_different_directory_fails``,
``test_same_relative_path_different_bytes_fails``,
``test_unregistered_historical_root_fails``,
``test_parent_traversal_is_rejected`` / ``test_symlink_escape_is_rejected``, and
``test_windows_and_posix_separators_yield_the_same_identity``.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from tools.natural_memory_benchmark.path_independent_identity import (
    HISTORICAL_WORKSPACE_ROOTS,
    ArtifactPathBinding,
    PathBindingViolation,
    build_binding_from_historical_path,
    normalize_separators,
    require_matching_binding,
    require_same_workspace_relative_path,
    resolve_within_workspace,
    sha256_path,
    workspace_relative_path,
)

HISTORICAL_ROOT = HISTORICAL_WORKSPACE_ROOTS[0]
RELATIVE = "artifacts/identity-memory-experiment/natural-v3-fresh/public.json"
CONTENT = b'{"case_count":12}\n'


def _workspace(tmp_path: Path, name: str, content: bytes = CONTENT) -> Path:
    """A workspace containing the artifact at its canonical relative position."""
    root = tmp_path / name
    target = root / RELATIVE
    target.parent.mkdir(parents=True)
    target.write_bytes(content)
    return root


def _binding(root: Path, *, role: str = "final_public", identity: str = "policy-v3") -> ArtifactPathBinding:
    return build_binding_from_historical_path(
        artifact_role=role,
        historical_absolute_path=f"{HISTORICAL_ROOT}/{RELATIVE}",
        workspace_root=root,
        artifact_identity=identity,
    )


def test_different_workspace_root_same_relative_path_and_hash_passes(
    tmp_path: Path,
) -> None:
    """The case the repair exists for: the workspace moved, nothing else changed."""
    first = _workspace(tmp_path, "workspace-a")
    second = _workspace(tmp_path, "workspace-b")
    assert first != second

    frozen = _binding(first)
    current = _binding(second)
    assert frozen.workspace_relative_path == RELATIVE
    assert frozen.content_sha256 == current.content_sha256
    require_matching_binding(frozen, current)


def test_same_basename_different_directory_fails(tmp_path: Path) -> None:
    """Position inside the workspace still matters; basename matching is refused."""
    root = tmp_path / "workspace"
    other_relative = "artifacts/identity-memory-experiment/dev-repair-v3/public.json"
    for relative in (RELATIVE, other_relative):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(CONTENT)

    frozen = _binding(root)
    moved = ArtifactPathBinding(
        artifact_role="final_public",
        workspace_relative_path=other_relative,
        content_sha256=frozen.content_sha256,
        artifact_identity="policy-v3",
    )
    assert Path(RELATIVE).name == Path(other_relative).name, "same basename"
    assert frozen.content_sha256 == moved.content_sha256, "identical bytes"

    with pytest.raises(PathBindingViolation) as error:
        require_matching_binding(frozen, moved)
    assert error.value.violation == "workspace_relative_path_mismatch"


def test_same_relative_path_different_bytes_fails(tmp_path: Path) -> None:
    first = _workspace(tmp_path, "workspace-a")
    second = _workspace(tmp_path, "workspace-b", content=b'{"case_count":13}\n')

    with pytest.raises(PathBindingViolation) as error:
        require_matching_binding(_binding(first), _binding(second))
    assert error.value.violation == "content_sha256_mismatch"


def test_same_content_and_path_but_different_role_fails(tmp_path: Path) -> None:
    """Role is part of identity: two roles are not interchangeable."""
    root = _workspace(tmp_path, "workspace")
    with pytest.raises(PathBindingViolation) as error:
        require_matching_binding(
            _binding(root, role="final_public"),
            _binding(root, role="dev_public"),
        )
    assert error.value.violation == "artifact_role_mismatch"


def test_same_content_and_path_but_different_policy_identity_fails(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path, "workspace")
    with pytest.raises(PathBindingViolation) as error:
        require_matching_binding(
            _binding(root, identity="policy-v3"),
            _binding(root, identity="policy-v4"),
        )
    assert error.value.violation == "artifact_identity_mismatch"


def test_unregistered_historical_root_fails() -> None:
    with pytest.raises(PathBindingViolation) as error:
        workspace_relative_path(f"/some/other/machine/{RELATIVE}")
    assert error.value.violation == "unknown_historical_workspace_root"


def test_suffix_matching_is_not_used(tmp_path: Path) -> None:
    """A path that merely *ends* with a known root must not be accepted."""
    with pytest.raises(PathBindingViolation) as error:
        workspace_relative_path(f"/elsewhere{HISTORICAL_ROOT}/{RELATIVE}")
    assert error.value.violation == "unknown_historical_workspace_root"


def test_parent_traversal_is_rejected() -> None:
    with pytest.raises(PathBindingViolation) as error:
        workspace_relative_path(f"{HISTORICAL_ROOT}/artifacts/../../escaped.json")
    assert error.value.violation == "parent_traversal"


def test_absolute_relative_path_is_rejected() -> None:
    # The validator raises PathBindingViolation directly rather than wrapping it in
    # a ValidationError, so the violation class stays visible to the caller.
    with pytest.raises(PathBindingViolation) as error:
        ArtifactPathBinding(
            artifact_role="final_public",
            workspace_relative_path="/absolute/public.json",
            content_sha256="a" * 64,
            artifact_identity="policy-v3",
        )
    assert error.value.violation == "absolute_relative_path"


def test_symlink_escape_is_rejected(tmp_path: Path) -> None:
    """Checked after resolution, so a contained-looking path cannot escape."""
    root = tmp_path / "workspace"
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "public.json").write_bytes(CONTENT)
    (root / "artifacts").mkdir(parents=True)
    os.symlink(outside, root / "artifacts" / "linked")

    with pytest.raises(PathBindingViolation) as error:
        resolve_within_workspace(root, "artifacts/linked/public.json")
    assert error.value.violation == "workspace_escape"


def test_contained_symlink_is_allowed(tmp_path: Path) -> None:
    """Only escapes are refused; a link that stays inside is fine."""
    root = tmp_path / "workspace"
    real = root / "artifacts" / "real"
    real.mkdir(parents=True)
    (real / "public.json").write_bytes(CONTENT)
    os.symlink(real, root / "artifacts" / "linked")

    resolved = resolve_within_workspace(root, "artifacts/linked/public.json")
    assert resolved.read_bytes() == CONTENT


def test_mixed_separators_are_normalized(tmp_path: Path) -> None:
    """A path with both separators must normalize too.

    The pure-Windows case is handled by ``PureWindowsPath``, so it passed even with
    the fallback replacement removed. A mixed path -- a POSIX prefix with Windows
    separators inside, which is what a record written by a tool joining paths on two
    platforms looks like -- exercises the replacement itself.
    """
    mixed = f"{HISTORICAL_ROOT}/artifacts\\identity-memory-experiment\\natural-v3-fresh\\public.json"
    assert "/" in mixed and "\\" in mixed
    assert normalize_separators(mixed) == f"{HISTORICAL_ROOT}/{RELATIVE}"
    assert workspace_relative_path(mixed) == RELATIVE

    root = _workspace(tmp_path, "workspace")
    mixed_binding = build_binding_from_historical_path(
        artifact_role="final_public",
        historical_absolute_path=mixed,
        workspace_root=root,
        artifact_identity="policy-v3",
    )
    assert mixed_binding.identity_key() == _binding(root).identity_key()


def test_windows_and_posix_separators_yield_the_same_identity(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path, "workspace")
    windows_style = f"{HISTORICAL_ROOT}/{RELATIVE}".replace("/", "\\")
    assert "\\" in windows_style

    posix = build_binding_from_historical_path(
        artifact_role="final_public",
        historical_absolute_path=f"{HISTORICAL_ROOT}/{RELATIVE}",
        workspace_root=root,
        artifact_identity="policy-v3",
    )
    windows = build_binding_from_historical_path(
        artifact_role="final_public",
        historical_absolute_path=windows_style,
        workspace_root=root,
        artifact_identity="policy-v3",
    )
    assert posix.identity_key() == windows.identity_key()
    assert normalize_separators(windows_style) == f"{HISTORICAL_ROOT}/{RELATIVE}"


def test_historical_locator_is_recorded_but_not_compared(tmp_path: Path) -> None:
    """The absolute path survives as history, never as identity."""
    first = _workspace(tmp_path, "workspace-a")
    second = _workspace(tmp_path, "workspace-b")
    frozen = _binding(first)
    current = _binding(second)

    assert frozen.historical_locator == f"{HISTORICAL_ROOT}/{RELATIVE}"
    assert frozen.historical_locator == current.historical_locator
    assert str(first) not in (frozen.historical_locator or "")
    require_matching_binding(frozen, current)


def test_relative_position_check_is_exact(tmp_path: Path) -> None:
    """The narrow helper the repaired call sites use."""
    derived = require_same_workspace_relative_path(
        artifact_role="final_public",
        frozen_absolute_path=f"{HISTORICAL_ROOT}/{RELATIVE}",
        expected_relative_path=RELATIVE,
    )
    assert derived == RELATIVE

    with pytest.raises(PathBindingViolation) as error:
        require_same_workspace_relative_path(
            artifact_role="final_public",
            frozen_absolute_path=f"{HISTORICAL_ROOT}/{RELATIVE}",
            expected_relative_path="artifacts/identity-memory-experiment/"
            "dev-repair-v3/public.json",
        )
    assert error.value.violation == "workspace_relative_path_mismatch"


def test_missing_artifact_in_current_workspace_fails(tmp_path: Path) -> None:
    empty = tmp_path / "empty-workspace"
    empty.mkdir()
    with pytest.raises(PathBindingViolation) as error:
        _binding(empty)
    assert error.value.violation == "artifact_missing_in_workspace"


def test_content_digest_is_measured_from_the_current_workspace(
    tmp_path: Path,
) -> None:
    root = _workspace(tmp_path, "workspace")
    binding = _binding(root)
    assert binding.content_sha256 == sha256_path(root / RELATIVE)
