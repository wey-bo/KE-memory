from pathlib import Path
import os


def write_env_local(path: Path, work_key: str, judge_key: str) -> None:
    if not work_key or not judge_key or "\n" in work_key or "\n" in judge_key:
        raise ValueError("Both API keys must be non-empty single-line values")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    try:
        payload = (
            f"KE_MEMORY_WORK_API_KEY={work_key}\nKE_MEMORY_JUDGE_API_KEY={judge_key}\n"
        ).encode()
        os.write(fd, payload)
    finally:
        os.close(fd)
    os.chmod(path, 0o600)
