from getpass import getpass
from pathlib import Path

from ke_memory_demo.infra.secrets import write_runtime_env_local


def main() -> None:
    write_runtime_env_local(
        Path(__file__).resolve().parents[1] / ".env.local",
        {
            "KE_MEMORY_WORK_API_KEY": getpass("Work-model API key: "),
            "KE_MEMORY_JUDGE_API_KEY": getpass("Judge API key: "),
            "KE_MEMORY_ES_URL": input("Elasticsearch URL: "),
            "KE_MEMORY_ES_INDEX": input("Elasticsearch index: "),
            "KE_MEMORY_ES_API_KEY": getpass("Elasticsearch API key: "),
        },
    )


if __name__ == "__main__":
    main()
