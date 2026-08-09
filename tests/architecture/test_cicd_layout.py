from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_cicd_foundation_files_are_present() -> None:
    required = (
        ".github/workflows/ci.yml",
        ".dockerignore",
        "Dockerfile",
        "Makefile",
        "scripts/ci/check.sh",
        "scripts/ci/verify_layout.py",
        "scripts/ci/verify_wheel.py",
    )
    assert [path for path in required if not (ROOT / path).is_file()] == []


def test_workflow_delegates_to_vendor_neutral_check_script() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    # The gate is delegation: the workflow names a script rather than inlining a
    # command list, so the local and remote entry points cannot drift apart.
    assert "scripts/ci/check-portable.sh" in workflow

    # KEOL must NOT be checked out here. It is private, so the default token gets a
    # 404 and the job dies before running anything -- observed on the first remote
    # run of this workflow. This assertion used to require the checkout and its
    # pinned SHA; it now requires their absence, so re-adding them without also
    # providing credentials fails here rather than on the runner.
    assert "genuineknowledge/KEOL" not in workflow

    portable_script = (ROOT / "scripts/ci/check-portable.sh").read_text(encoding="utf-8")
    assert "scripts/ci/verify_wheel.py" in portable_script
    # Read past the comments: the prose explains why KEOL is absent, so a plain
    # substring check would match its own explanation. What must hold is that no
    # executable line consumes the variable.
    portable_code = [
        line for line in portable_script.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    assert not [line for line in portable_code if "KEOL_SOURCE" in line]

    # check.sh stays the local entry point and keeps the pinned KEOL contract, so
    # the bridge test still has an authoritative way to run.
    check_script = (ROOT / "scripts/ci/check.sh").read_text(encoding="utf-8")
    assert "scripts/ci/verify_wheel.py" in check_script
    assert "KEOL_SOURCE" in check_script


def test_container_is_non_root_and_persists_state() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER ke-memory" in dockerfile
    assert 'VOLUME ["/app/state"]' in dockerfile
    assert "HEALTHCHECK" in dockerfile
