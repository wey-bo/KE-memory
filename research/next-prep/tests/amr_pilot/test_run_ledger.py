from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import pytest

from tools.amr_pilot.models import AttemptSidecar
from tools.amr_pilot.run_ledger import write_attempt


RAW = "(c / cancel-01)"


def sidecar(*, attempt: int = 1, parse_status: str = "valid", previous: str | None = None) -> AttemptSidecar:
    started = datetime(2026, 7, 24, 12, 0, 0, tzinfo=timezone.utc)
    finished = datetime(2026, 7, 24, 12, 0, 1, tzinfo=timezone.utc)
    return AttemptSidecar.model_validate(
        {
            "sample_id": "AMR-S001",
            "route": "A",
            "run_id": "run-20260724T120000Z",
            "attempt": attempt,
            "previous_attempt_sha256": previous,
            "model_id": "gpt-5.6-terra",
            "prompt_sha256": "1" * 64,
            "raw_output_sha256": hashlib.sha256(RAW.encode("utf-8")).hexdigest(),
            "started_at": started,
            "finished_at": finished,
            "latency_ms": 1000,
            "usage": {"status": "unavailable", "reason": "interface did not expose telemetry"},
            "parse_status": parse_status,
            "parse_errors": [] if parse_status == "valid" else ["parse failed"],
            "representation_gaps": [],
        }
    )


def test_attempt_writes_raw_sidecar_and_hash_record(tmp_path: Path) -> None:
    result = write_attempt(tmp_path, RAW, sidecar())

    assert result.raw_path.read_text(encoding="utf-8") == RAW
    document = json.loads(result.sidecar_path.read_text(encoding="utf-8"))
    assert document["usage"]["status"] == "unavailable"
    assert document["latency_ms"] == 1000
    assert result.raw_sha256 == hashlib.sha256(RAW.encode("utf-8")).hexdigest()
    assert result.sidecar_sha256 == hashlib.sha256(result.sidecar_path.read_bytes()).hexdigest()


def test_attempt_files_are_immutable(tmp_path: Path) -> None:
    write_attempt(tmp_path, RAW, sidecar())

    with pytest.raises(ValueError, match="refusing to overwrite"):
        write_attempt(tmp_path, RAW, sidecar())


def test_raw_hash_must_match_sidecar(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="raw_output_sha256"):
        write_attempt(tmp_path, "(d / different)", sidecar())


def test_second_attempt_requires_first_attempt_parse_failure(tmp_path: Path) -> None:
    first = write_attempt(tmp_path, RAW, sidecar(parse_status="valid"))
    second = sidecar(attempt=2, previous=first.sidecar_sha256)

    with pytest.raises(ValueError, match="parse failure"):
        write_attempt(tmp_path, RAW, second)


def test_second_attempt_binds_failed_first_sidecar_hash(tmp_path: Path) -> None:
    first = write_attempt(tmp_path, RAW, sidecar(parse_status="invalid"))

    with pytest.raises(ValueError, match="previous_attempt_sha256"):
        write_attempt(tmp_path, RAW, sidecar(attempt=2, previous="3" * 64))

    second = write_attempt(
        tmp_path,
        RAW,
        sidecar(attempt=2, previous=first.sidecar_sha256),
    )
    assert second.sidecar_path.exists()


def test_second_attempt_is_rejected_when_first_attempt_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="attempt 1 is missing"):
        write_attempt(tmp_path, RAW, sidecar(attempt=2, previous="3" * 64))
