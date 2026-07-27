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
    )
    assert [path for path in required if not (ROOT / path).is_file()] == []


def test_workflow_delegates_to_vendor_neutral_check_script() -> None:
    workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "scripts/ci/check.sh" in workflow
    assert "genuineknowledge/KEOL" in workflow
    assert "44631e64fd07c9b85f22e36035bf49c882dba592" in workflow


def test_container_is_non_root_and_persists_state() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER ke-memory" in dockerfile
    assert 'VOLUME ["/app/state"]' in dockerfile
    assert "HEALTHCHECK" in dockerfile

