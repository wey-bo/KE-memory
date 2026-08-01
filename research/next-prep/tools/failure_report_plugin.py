"""Pytest plugin that records each failure's nodeid and crash reason as JSON.

Parsing pytest's human-readable output is unreliable: parametrized nodeids
contain spaces and brackets, and the short summary carries no reason text at
all. Reading the report objects directly gives the exact nodeid alongside the
exception type and message, which is what per-entry classification needs.

Enabled explicitly with ``-p`` and writes to the path in
``FAILURE_REPORT_JSON``; it is not a conftest, so it cannot affect a normal run.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

_RECORDS: dict[str, dict[str, Any]] = {}

# The last exception line in a child's captured stderr is its real reason. Anchored
# on the exception name so ordinary log text containing a colon is not mistaken
# for one.
_CHILD_ERROR = re.compile(
    r"(?:ValueError|RuntimeError|AssertionError|KeyError|TypeError|FileNotFoundError|"
    r"FileExistsError|ModuleNotFoundError|ImportError|OSError): [^\\\n\"']+"
)


def pytest_runtest_logreport(report: Any) -> None:
    if not report.failed:
        return
    # A test can fail in setup and again in teardown; keep the first, which is
    # the cause rather than the consequence.
    if report.nodeid in _RECORDS:
        return
    longrepr = getattr(report, "longrepr", None)
    crash = getattr(longrepr, "reprcrash", None)
    message = (crash.message if crash is not None else str(longrepr))[:600]
    # A CalledProcessError tells the parent only that a child exited non-zero.
    # The child's own reason is in the captured stderr inside the full repr, so
    # carry that along or the failure cannot be classified at all.
    full = str(longrepr)
    child_reason = ""
    if "CalledProcessError" in message:
        for match in _CHILD_ERROR.finditer(full):
            child_reason = match.group(0)
    _RECORDS[report.nodeid] = {
        "nodeid": report.nodeid,
        "when": report.when,
        "message": message,
        "child_reason": child_reason[:300],
        "path": crash.path if crash is not None else "",
    }


def pytest_sessionfinish(session: Any, exitstatus: int) -> None:
    target = os.environ.get("FAILURE_REPORT_JSON")
    if not target:
        return
    payload = {
        "failure_count": len(_RECORDS),
        "failures": [_RECORDS[key] for key in sorted(_RECORDS)],
    }
    Path(target).write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
