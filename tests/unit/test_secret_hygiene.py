from pathlib import Path
import stat

import pytest

from ke_memory_demo.infra.secrets import write_env_local


def test_write_env_local_is_private_and_complete(tmp_path: Path):
    target = tmp_path / ".env.local"
    write_env_local(target, "work-test-value", "judge-test-value")
    assert stat.S_IMODE(target.stat().st_mode) == 0o600
    assert target.read_text().splitlines() == [
        "KE_MEMORY_WORK_API_KEY=work-test-value",
        "KE_MEMORY_JUDGE_API_KEY=judge-test-value",
    ]


@pytest.mark.parametrize(
    ("work_key", "judge_key"),
    [
        ("", "judge-test-value"),
        ("work-test-value", ""),
        ("work-test-value\nsecond-line", "judge-test-value"),
        ("work-test-value", "judge-test-value\nsecond-line"),
    ],
)
def test_write_env_local_rejects_empty_or_multiline_keys(
    tmp_path: Path,
    work_key: str,
    judge_key: str,
):
    with pytest.raises(ValueError, match="non-empty single-line"):
        write_env_local(tmp_path / ".env.local", work_key, judge_key)


def test_write_env_local_repairs_permissions_on_an_existing_file(tmp_path: Path):
    target = tmp_path / ".env.local"
    target.write_text("old-value")
    target.chmod(0o644)

    write_env_local(target, "work-test-value", "judge-test-value")

    assert stat.S_IMODE(target.stat().st_mode) == 0o600
