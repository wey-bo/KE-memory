from getpass import getpass
from pathlib import Path

from ke_memory_demo.infra.secrets import write_env_local


write_env_local(
    Path(".env.local"),
    work_key=getpass("Work-model API key: "),
    judge_key=getpass("Judge API key: "),
)
