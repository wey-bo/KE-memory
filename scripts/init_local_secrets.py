from getpass import getpass
from pathlib import Path

from ke_memory_demo.infra.secrets import write_env_local


def main() -> None:
    write_env_local(
        Path(__file__).resolve().parents[1] / ".env.local",
        work_key=getpass("Work-model API key: "),
        judge_key=getpass("Judge API key: "),
    )


if __name__ == "__main__":
    main()
