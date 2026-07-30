from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Literal
from urllib.request import urlopen

from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import typed_extractor_fresh_v3_authoring as authoring
from .io import (
    canonical_json_bytes,
    load_json,
    sha256_file,
    write_json_immutable,
    write_text_immutable,
)
from .typed_extractor_fresh_v3_proposer_freeze import (
    ISOLATION_CONTEXT,
    PROMPT_PATHS,
    PROMPT_SHA256,
    PUBLIC_SHA256,
)
from .typed_extractor_fresh_v3_qualification import (
    L1_QUALITY_METRICS,
    L2_QUALITY_METRICS,
    SAFETY_COUNTS,
    V3_L1_OUTPUTS,
    V3_L2_OUTPUTS,
    V3_L2_THRESHOLDS,
    validate_fresh_v3_qualification,
)
from .typed_extractor_l1 import L1ProposalPayload, run_l1_scoring_file
from .typed_extractor_l1_api_run import run_l1_openai_compatible_proposer
from .typed_extractor_l2 import L2ProposalPayload, run_l2_scoring_file
from .typed_extractor_l2_api_run import run_l2_openai_compatible_proposer
from .typed_extractor_model_run import (
    L1ModelDispatch,
    L1ModelProvenance,
    _validate_dispatch as _validate_l1_dispatch,
    extract_l1_proposal_payload,
    freeze_l1_model_proposals,
    write_l1_model_dispatch,
)
from .typed_extractor_l2_model_run import (
    L2ModelDispatch,
    L2ModelProvenance,
    _validate_dispatch as _validate_l2_dispatch,
    extract_l2_proposal_payload,
    freeze_l2_model_proposals,
    write_l2_model_dispatch,
)


Layer = Literal["l1", "l2"]

REQUESTED_MODEL = "deepseek-v4-pro"
EVALUATION_ID = "typed-extractor-v3-fresh-hidden-v1-deepseek-v4-pro-rerun-v1"
ORIGINAL_RELATIVE_ROOT = (
    "artifacts/automatic-extraction-assessment/typed-extractor-v3-fresh-hidden-v1"
)
RERUN_RELATIVE_ROOT = (
    "artifacts/automatic-extraction-assessment/"
    "typed-extractor-v3-fresh-hidden-v1-deepseek-v4-pro-rerun-v1"
)
ORIGINAL_FACT_COMMIT = "252e3d9055a191c1434abb8f6308761fe3a2b9c9"
ORIGINAL_BINDINGS = {
    "overall-score.json": (
        "28b0719b767328c45dde84ebe8a025b2747bb8a41acd6d4f67eb75eec6b9c8ef"
    ),
    "overall-report.md": (
        "04b814d02c2715ba446f668628fcb2d7c6a4cae3bed77199da3cf0db0261e883"
    ),
    "qualification-chronology.json": (
        "2a7d1653213ba74574cb2bb7fc1ee7394e22227ef0c5ab692f2a9438619420d0"
    ),
}
PROPOSER_ID = "deepseek-official-api"
PROPOSER_VERSIONS = {
    "l1": "deepseek-v4-pro@ustc-api-2026-07-30-fresh-v3-rerun-l1",
    "l2": "deepseek-v4-pro@ustc-api-2026-07-30-fresh-v3-rerun-l2",
}
CASE_COUNTS = {"l1": 24, "l2": 18}
ARTIFACT_FILES = (
    "dispatch.json",
    "raw-response.json",
    "proposals.json",
    "provenance.json",
)
SUCCESS_FILES = {*ARTIFACT_FILES, "proposal-freeze-receipt.json"}
FAILURE_FILES = {"dispatch.json", "proposal-freeze-failure-receipt.json"}
POST_SCORE_FILES = {
    *SUCCESS_FILES,
    "score.json",
    "error-analysis.json",
    "report.md",
    "qualification.json",
}
OVERALL_FILES = {
    "preflight-receipt.json",
    "overall-score.json",
    "overall-report.md",
    "qualification-chronology.json",
}
IMPLEMENTATION_PATHS = {
    "typed_extractor_fresh_v3_v4pro_rerun.py": (
        "tools/natural_memory_benchmark/typed_extractor_fresh_v3_v4pro_rerun.py"
    ),
    "test_typed_extractor_fresh_v3_v4pro_rerun.py": (
        "tests/natural_memory_benchmark/"
        "test_typed_extractor_fresh_v3_v4pro_rerun.py"
    ),
    "typed_extractor_l1.py": "tools/natural_memory_benchmark/typed_extractor_l1.py",
    "typed_extractor_l2.py": "tools/natural_memory_benchmark/typed_extractor_l2.py",
}


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FrozenArtifact(StrictModel):
    filename: str = Field(pattern=r"^[^/\\]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    mode: Literal["0444"] = "0444"


class ProposalFreezeReceipt(StrictModel):
    schema_version: Literal["typed-extractor-fresh-v3-v4pro-proposal-freeze-v1"] = (
        "typed-extractor-fresh-v3-v4pro-proposal-freeze-v1"
    )
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal[
        "typed-extractor-v3-fresh-hidden-v1-deepseek-v4-pro-rerun-v1"
    ] = EVALUATION_ID
    layer: Layer
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    request_count: Literal[1] = 1
    request_ordinal: Literal[1] = 1
    requested_model: Literal["deepseek-v4-pro"] = REQUESTED_MODEL
    response_model: str = Field(min_length=1)
    isolation_context: Literal["fresh-agent-no-history-declarative"] = (
        ISOLATION_CONTEXT
    )
    history_context_inherited: Literal[False] = False
    authority_or_gold_read_before_freeze: Literal[False] = False
    preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_bindings: dict[str, str]
    implementation_sha256: dict[str, str]
    artifacts: dict[str, FrozenArtifact]
    automatic_write_counts: dict[str, int]
    freeze_sequence: tuple[
        Literal["dispatch"],
        Literal["raw_response"],
        Literal["proposals"],
        Literal["provenance"],
    ] = ("dispatch", "raw_response", "proposals", "provenance")

    @model_validator(mode="after")
    def validate_contract(self) -> "ProposalFreezeReceipt":
        if self.case_count != CASE_COUNTS[self.layer]:
            raise ValueError("proposal receipt case count mismatch")
        if set(self.artifacts) != set(ARTIFACT_FILES):
            raise ValueError("proposal receipt artifact registry mismatch")
        if self.automatic_write_counts != authoring.AUTOMATIC_WRITE_COUNTS:
            raise ValueError("proposal receipt write boundary mismatch")
        return self


class ProposalFailureReceipt(StrictModel):
    schema_version: Literal["typed-extractor-fresh-v3-v4pro-proposal-failure-v1"] = (
        "typed-extractor-fresh-v3-v4pro-proposal-failure-v1"
    )
    status: Literal["frozen_failure"] = "frozen_failure"
    evaluation_id: Literal[
        "typed-extractor-v3-fresh-hidden-v1-deepseek-v4-pro-rerun-v1"
    ] = EVALUATION_ID
    layer: Layer
    run_id: str = Field(min_length=1)
    request_count: Literal[1] = 1
    request_ordinal: Literal[1] = 1
    requested_model: Literal["deepseek-v4-pro"] = REQUESTED_MODEL
    failure_type: str = Field(min_length=1)
    failure_message: str = Field(min_length=1)
    retry_performed: Literal[False] = False
    fallback_model_used: Literal[False] = False
    preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    original_bindings: dict[str, str]
    implementation_sha256: dict[str, str]
    artifacts: dict[str, FrozenArtifact]


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _run_git(repository_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode:
        detail = completed.stderr.decode(errors="replace").strip()
        raise ValueError(f"Git command failed: {' '.join(args)}: {detail}")
    return completed.stdout


def _roots(repository_root: Path, workspace_root: Path) -> tuple[Path, Path, Path, Path]:
    repository_root = Path(os.path.abspath(os.fspath(repository_root)))
    workspace_root = Path(os.path.abspath(os.fspath(workspace_root)))
    if workspace_root != repository_root / "research/next-prep":
        raise ValueError("workspace root mismatch")
    return (
        repository_root,
        workspace_root,
        workspace_root / ORIGINAL_RELATIVE_ROOT,
        workspace_root / RERUN_RELATIVE_ROOT,
    )


def _require_layer(layer: str) -> Layer:
    if layer not in ("l1", "l2"):
        raise ValueError("layer must be l1 or l2")
    return layer


def _read_immutable(path: Path, label: str) -> bytes:
    opened = path.lstat()
    if not stat.S_ISREG(opened.st_mode) or stat.S_ISLNK(opened.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    if stat.S_IMODE(opened.st_mode) != 0o444:
        raise ValueError(f"{label} must have mode 0444")
    content = path.read_bytes()
    rechecked = path.lstat()
    if (opened.st_dev, opened.st_ino, opened.st_size) != (
        rechecked.st_dev,
        rechecked.st_ino,
        rechecked.st_size,
    ):
        raise ValueError(f"{label} changed while reading")
    return content


def _artifact(path: Path) -> FrozenArtifact:
    content = _read_immutable(path, path.name)
    return FrozenArtifact(
        filename=path.name,
        sha256=_sha256_bytes(content),
        size_bytes=len(content),
    )


def _implementation_bindings(
    repository_root: Path, workspace_root: Path
) -> dict[str, str]:
    result: dict[str, str] = {}
    for name, relative in IMPLEMENTATION_PATHS.items():
        committed = _run_git(
            repository_root, "show", f"HEAD:research/next-prep/{relative}"
        )
        current = (workspace_root / relative).read_bytes()
        if committed != current:
            raise ValueError(f"committed implementation bytes drift: {name}")
        result[name] = _sha256_bytes(committed)
    return result


def _current_bindings(
    repository_root: Path,
    workspace_root: Path,
    original_root: Path,
) -> dict[str, Any]:
    original = validate_fresh_v3_qualification(repository_root, workspace_root)
    if original["status"] != "incomplete_not_qualified":
        raise ValueError("original qualification conclusion drift")
    for name, expected in ORIGINAL_BINDINGS.items():
        if sha256_file(original_root / name) != expected:
            raise ValueError(f"original qualification artifact drift: {name}")
    for layer in ("l1", "l2"):
        if sha256_file(workspace_root / PROMPT_PATHS[layer]) != PROMPT_SHA256[layer]:
            raise ValueError(f"{layer} prompt drift")
        public = original_root / layer / f"public-{layer}.json"
        if sha256_file(public) != PUBLIC_SHA256[layer]:
            raise ValueError(f"{layer} public input drift")
    _run_git(repository_root, "diff", "--cached", "--quiet")
    _run_git(
        repository_root,
        "merge-base",
        "--is-ancestor",
        ORIGINAL_FACT_COMMIT,
        "HEAD",
    )
    protected = authoring._protected_state(workspace_root)
    result = {
        "status": "valid",
        "head": _run_git(repository_root, "rev-parse", "HEAD")
        .decode("ascii")
        .strip(),
        "requested_model": REQUESTED_MODEL,
        "original_fact_commit": ORIGINAL_FACT_COMMIT,
        "original_bindings": dict(ORIGINAL_BINDINGS),
        "prompt_sha256": dict(PROMPT_SHA256),
        "public_sha256": dict(PUBLIC_SHA256),
        "implementation_sha256": _implementation_bindings(
            repository_root, workspace_root
        ),
        "candidate_v3_queue_sha256": authoring.CANDIDATE_QUEUE_SHA256,
        "guard_fingerprint": authoring.GUARD_FINGERPRINT,
        "guard_results_sha256": protected["guard_results_sha256"],
        "guard_counts": protected["guard_counts"],
        "automatic_write_counts": dict(authoring.AUTOMATIC_WRITE_COUNTS),
    }
    result["preflight_sha256"] = _sha256_bytes(canonical_json_bytes(result))
    return result


def validate_v4pro_rerun_preflight(
    repository_root: Path, workspace_root: Path
) -> dict[str, Any]:
    repository_root, workspace_root, original_root, rerun_root = _roots(
        repository_root, workspace_root
    )
    if rerun_root.exists():
        raise ValueError("rerun result root must be absent")
    return _current_bindings(repository_root, workspace_root, original_root)


def run_ids(run_label: str) -> dict[str, str]:
    try:
        parsed = datetime.strptime(run_label, "%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError) as error:
        raise ValueError("invalid run label") from error
    if parsed.strftime("%Y%m%dT%H%M%SZ") != run_label:
        raise ValueError("invalid run label")
    return {
        layer: (
            f"run-{run_label}-deepseek-v4-pro-typed-{layer}-"
            "fresh-hidden-v3-rerun"
        )
        for layer in ("l1", "l2")
    }


def _write_preflight(rerun_root: Path, state: dict[str, Any]) -> None:
    write_json_immutable(rerun_root / "preflight-receipt.json", state)
    (rerun_root / "preflight-receipt.json").chmod(0o444)


def _load_preflight(rerun_root: Path) -> dict[str, Any]:
    content = _read_immutable(
        rerun_root / "preflight-receipt.json", "rerun preflight receipt"
    )
    payload = json.loads(content)
    if content != canonical_json_bytes(payload):
        raise ValueError("rerun preflight receipt is not canonical JSON")
    if payload.get("requested_model") not in (None, REQUESTED_MODEL):
        raise ValueError("rerun preflight model drift")
    return payload


def _dispatch_paths(
    workspace_root: Path,
    original_root: Path,
    rerun_root: Path,
    layer: Layer,
    run_id: str,
) -> tuple[Path, Path, Path]:
    return (
        original_root / layer / f"public-{layer}.json",
        workspace_root / PROMPT_PATHS[layer],
        rerun_root / layer / "model-runs" / run_id,
    )


def freeze_v4pro_rerun_dispatches(
    repository_root: Path, workspace_root: Path, run_label: str
) -> dict[str, Any]:
    ids = run_ids(run_label)
    state = validate_v4pro_rerun_preflight(repository_root, workspace_root)
    _, workspace_root, original_root, rerun_root = _roots(
        repository_root, workspace_root
    )
    rerun_root.mkdir(mode=0o775)
    rerun_root.chmod(0o775)
    _write_preflight(rerun_root, state)
    dispatches: dict[str, Any] = {}
    for raw_layer in ("l1", "l2"):
        layer = _require_layer(raw_layer)
        public, prompt, run_root = _dispatch_paths(
            workspace_root, original_root, rerun_root, layer, ids[layer]
        )
        run_root.mkdir(parents=True, mode=0o775)
        run_root.parent.chmod(0o775)
        run_root.parent.parent.chmod(0o775)
        run_root.chmod(0o775)
        writer = write_l1_model_dispatch if layer == "l1" else write_l2_model_dispatch
        dispatches[layer] = writer(
            public,
            prompt,
            run_root / "dispatch.json",
            run_id=ids[layer],
            proposer_id=PROPOSER_ID,
            proposer_version=PROPOSER_VERSIONS[layer],
            requested_model=REQUESTED_MODEL,
            isolation_context=ISOLATION_CONTEXT,
        )
    return {
        "status": "dispatches_frozen",
        "run_ids": ids,
        "preflight_sha256": state["preflight_sha256"],
        "dispatches": dispatches,
    }


def _discover_runs(rerun_root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for layer in ("l1", "l2"):
        model_runs = rerun_root / layer / "model-runs"
        children = list(model_runs.iterdir())
        if len(children) != 1 or not children[0].is_dir():
            raise ValueError(f"{layer} must contain exactly one rerun")
        result[layer] = children[0]
    return result


def _validate_dispatch(
    workspace_root: Path,
    original_root: Path,
    layer: Layer,
    run_root: Path,
) -> dict[str, Any]:
    public = original_root / layer / f"public-{layer}.json"
    prompt = workspace_root / PROMPT_PATHS[layer]
    content = _read_immutable(run_root / "dispatch.json", f"{layer} dispatch")
    if layer == "l1":
        dispatch: Any = L1ModelDispatch.model_validate_json(content, strict=True)
        _validate_l1_dispatch(
            dispatch,
            public_path=public,
            prompt_path=prompt,
            isolation_context=ISOLATION_CONTEXT,
        )
    else:
        dispatch = L2ModelDispatch.model_validate_json(content, strict=True)
        _validate_l2_dispatch(
            dispatch,
            public_path=public,
            prompt_path=prompt,
            isolation_context=ISOLATION_CONTEXT,
        )
    if content != canonical_json_bytes(dispatch):
        raise ValueError(f"{layer} dispatch is not canonical JSON")
    if dispatch.requested_model != REQUESTED_MODEL:
        raise ValueError(f"{layer} requested model drift")
    return dispatch.model_dump(mode="json")


def _failure_receipt(
    run_root: Path,
    layer: Layer,
    state: dict[str, Any],
    error: Exception,
) -> None:
    receipt = ProposalFailureReceipt(
        layer=layer,
        run_id=run_root.name,
        failure_type=type(error).__name__,
        failure_message=str(error) or type(error).__name__,
        preflight_sha256=state["preflight_sha256"],
        original_bindings=dict(state["original_bindings"]),
        implementation_sha256=dict(state["implementation_sha256"]),
        artifacts={
            name: _artifact(run_root / name)
            for name in ARTIFACT_FILES
            if (run_root / name).is_file()
        },
    )
    path = run_root / "proposal-freeze-failure-receipt.json"
    write_json_immutable(path, receipt)
    path.chmod(0o444)


def run_and_freeze_v4pro_layer(
    repository_root: Path,
    workspace_root: Path,
    layer: Layer,
    *,
    base_url: str,
    api_key: str,
    timeout_seconds: int,
    opener: Callable[..., Any] = urlopen,
) -> dict[str, Any]:
    layer = _require_layer(layer)
    if not base_url or not api_key:
        raise ValueError("base URL and API key are required")
    if isinstance(timeout_seconds, bool) or timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    _, workspace_root, original_root, rerun_root = _roots(
        repository_root, workspace_root
    )
    state = _load_preflight(rerun_root)
    runs = _discover_runs(rerun_root)
    for checked_layer in ("l1", "l2"):
        _validate_dispatch(
            workspace_root,
            original_root,
            _require_layer(checked_layer),
            runs[checked_layer],
        )
    run_root = runs[layer]
    if {path.name for path in run_root.iterdir()} != {"dispatch.json"}:
        raise ValueError(f"{layer} formal run has already been attempted")
    public = original_root / layer / f"public-{layer}.json"
    prompt = workspace_root / PROMPT_PATHS[layer]
    try:
        with tempfile.TemporaryDirectory(prefix=f"ke-memory-v4pro-{layer}-") as temp:
            staged = Path(temp) / "proposals.json"
            common = {
                "public_path": public,
                "prompt_path": prompt,
                "dispatch_path": run_root / "dispatch.json",
                "raw_response_path": run_root / "raw-response.json",
                "staged_proposals_path": staged,
                "base_url": base_url,
                "api_key": api_key,
                "model": REQUESTED_MODEL,
                "timeout_seconds": timeout_seconds,
                "opener": opener,
            }
            if layer == "l1":
                run_l1_openai_compatible_proposer(**common)
                freeze_l1_model_proposals(
                    public,
                    staged,
                    run_root / "proposals.json",
                    run_root / "provenance.json",
                    prompt_path=prompt,
                    dispatch_path=run_root / "dispatch.json",
                    raw_response_path=run_root / "raw-response.json",
                    isolation_context=ISOLATION_CONTEXT,
                )
            else:
                run_l2_openai_compatible_proposer(**common)
                freeze_l2_model_proposals(
                    public,
                    staged,
                    run_root / "proposals.json",
                    run_root / "provenance.json",
                    prompt_path=prompt,
                    dispatch_path=run_root / "dispatch.json",
                    raw_response_path=run_root / "raw-response.json",
                    isolation_context=ISOLATION_CONTEXT,
                )
        raw = load_json(run_root / "raw-response.json")
        response_model = raw.get("model")
        if not isinstance(response_model, str) or not response_model:
            raise ValueError("raw response model missing")
        dispatch = load_json(run_root / "dispatch.json")
        receipt = ProposalFreezeReceipt(
            layer=layer,
            dataset_id=dispatch["dataset_id"],
            case_count=dispatch["case_count"],
            run_id=dispatch["run_id"],
            response_model=response_model,
            preflight_sha256=state["preflight_sha256"],
            original_bindings=dict(state["original_bindings"]),
            implementation_sha256=dict(state["implementation_sha256"]),
            artifacts={name: _artifact(run_root / name) for name in ARTIFACT_FILES},
            automatic_write_counts=dict(authoring.AUTOMATIC_WRITE_COUNTS),
        )
        receipt_path = run_root / "proposal-freeze-receipt.json"
        write_json_immutable(receipt_path, receipt)
        receipt_path.chmod(0o444)
    except Exception as error:
        try:
            _failure_receipt(run_root, layer, state, error)
        except Exception as receipt_error:
            error.add_note(f"failure receipt could not be frozen: {receipt_error}")
        raise
    return validate_v4pro_proposal_freeze(repository_root, workspace_root, layer)


def validate_v4pro_proposal_freeze(
    repository_root: Path, workspace_root: Path, layer: Layer
) -> dict[str, Any]:
    layer = _require_layer(layer)
    _, workspace_root, original_root, rerun_root = _roots(
        repository_root, workspace_root
    )
    state = _load_preflight(rerun_root)
    run_root = _discover_runs(rerun_root)[layer]
    if {path.name for path in run_root.iterdir()} != SUCCESS_FILES:
        raise ValueError(f"{layer} proposal freeze artifact set mismatch")
    dispatch = _validate_dispatch(workspace_root, original_root, layer, run_root)
    receipt_content = _read_immutable(
        run_root / "proposal-freeze-receipt.json", f"{layer} proposal receipt"
    )
    receipt = ProposalFreezeReceipt.model_validate_json(receipt_content, strict=True)
    if receipt_content != canonical_json_bytes(receipt):
        raise ValueError(f"{layer} proposal receipt is not canonical JSON")
    if (
        receipt.run_id != run_root.name
        or receipt.preflight_sha256 != state["preflight_sha256"]
        or receipt.original_bindings != state["original_bindings"]
        or receipt.implementation_sha256 != state["implementation_sha256"]
        or dispatch["requested_model"] != receipt.requested_model
    ):
        raise ValueError(f"{layer} proposal receipt binding drift")
    for name, binding in receipt.artifacts.items():
        path = run_root / name
        if (
            sha256_file(path) != binding.sha256
            or path.stat().st_size != binding.size_bytes
        ):
            raise ValueError(f"{layer} proposal artifact drift: {name}")
    raw = load_json(run_root / "raw-response.json")
    frozen = load_json(run_root / "proposals.json")
    if layer == "l1":
        parsed: Any = extract_l1_proposal_payload(raw)
        proposals = L1ProposalPayload.model_validate(frozen, strict=True)
        provenance: Any = L1ModelProvenance.model_validate_json(
            _read_immutable(run_root / "provenance.json", "l1 provenance"),
            strict=True,
        )
    else:
        parsed = extract_l2_proposal_payload(raw)
        proposals = L2ProposalPayload.model_validate(frozen, strict=True)
        provenance = L2ModelProvenance.model_validate_json(
            _read_immutable(run_root / "provenance.json", "l2 provenance"),
            strict=True,
        )
    if parsed.model_dump(mode="json") != proposals.model_dump(mode="json"):
        raise ValueError(f"{layer} raw response/proposal replay mismatch")
    if (
        provenance.requested_model != REQUESTED_MODEL
        or provenance.response_model != receipt.response_model
    ):
        raise ValueError(f"{layer} provenance model drift")
    return {
        "status": "valid",
        "layer": layer,
        "run_id": run_root.name,
        "run_root": str(run_root),
        "request_count": 1,
        "requested_model": REQUESTED_MODEL,
        "response_model": receipt.response_model,
        "receipt_sha256": sha256_file(run_root / "proposal-freeze-receipt.json"),
    }


def _number_equals(value: Any, expected: float | int) -> bool:
    return not isinstance(value, bool) and isinstance(value, (int, float)) and value == expected


def build_layer_qualification(
    layer: Layer,
    score: dict[str, Any],
    receipt: dict[str, Any],
    score_sha256: str,
) -> dict[str, Any]:
    layer = _require_layer(layer)
    quality_names = L1_QUALITY_METRICS if layer == "l1" else L2_QUALITY_METRICS
    metrics = score.get("metrics")
    if not isinstance(metrics, dict):
        raise ValueError(f"{layer} score metrics missing")
    quality_checks = {name: _number_equals(metrics.get(name), 1.0) for name in quality_names}
    safety_checks = {name: _number_equals(metrics.get(name), 0) for name in SAFETY_COUNTS}
    raw_ready = (
        all(quality_checks.values())
        and safety_checks["raw_critical_false_emission_count"]
        and score.get("raw_proposer_quality_ready") is True
    )
    gate_ready = (
        safety_checks["gate_intervention_count"]
        and safety_checks["deterministic_critical_false_materialization_count"]
        and score.get("deterministic_gate_safety_ready") is True
    )
    layer_ready = raw_ready and gate_ready
    return {
        "schema_version": "typed-extractor-fresh-v3-v4pro-layer-qualification-v1",
        "status": "qualified" if layer_ready else "not_qualified",
        "evaluation_id": EVALUATION_ID,
        "layer": layer,
        "dataset_id": score["dataset_id"],
        "run_id": score["run_id"],
        "case_count": score["case_count"],
        "proposal_freeze_receipt_sha256": receipt["receipt_sha256"],
        "score_sha256": score_sha256,
        "requested_model": REQUESTED_MODEL,
        "response_model": receipt["response_model"],
        "request_count": receipt["request_count"],
        "metrics": metrics,
        "quality_checks": quality_checks,
        "safety_checks": safety_checks,
        "scorer_raw_proposer_quality_ready": score.get("raw_proposer_quality_ready") is True,
        "scorer_deterministic_gate_safety_ready": score.get("deterministic_gate_safety_ready") is True,
        "raw_proposer_quality_ready": raw_ready,
        "deterministic_gate_safety_ready": gate_ready,
        "layer_ready": layer_ready,
        "automatic_write_counts": dict(authoring.AUTOMATIC_WRITE_COUNTS),
        "pipeline_integration_authorized": False,
        "authoritative_writes_authorized": False,
    }


def _validate_time(value: str) -> str:
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError) as error:
        raise ValueError("invalid qualification time") from error
    if parsed.strftime("%Y-%m-%dT%H:%M:%SZ") != value:
        raise ValueError("invalid qualification time")
    return value


def _overall_report(overall: dict[str, Any]) -> str:
    lines = [
        "# Typed Extractor Fresh-V3 DeepSeek-V4-Pro Rerun Qualification",
        "",
        f"- Conclusion: `{overall['status']}`",
        f"- Qualification time: `{overall['qualification_time']}`",
        "",
    ]
    for layer in ("l1", "l2"):
        item = overall["layers"][layer]
        lines.extend(
            [
                f"- {layer.upper()} status: `{item['status']}`",
                f"- {layer.upper()} raw proposer quality ready: `{str(item.get('raw_proposer_quality_ready', False)).lower()}`",
                f"- {layer.upper()} deterministic gate safety ready: `{str(item.get('deterministic_gate_safety_ready', False)).lower()}`",
            ]
        )
    lines.extend(
        [
            "",
            "No pipeline integration or authoritative memory write is authorized.",
            "",
        ]
    )
    return "\n".join(lines)


def _freeze_overall(
    rerun_root: Path,
    overall: dict[str, Any],
    receipts: dict[str, str],
    scores: dict[str, str],
    qualifications: dict[str, str],
) -> None:
    score_path = rerun_root / "overall-score.json"
    write_json_immutable(score_path, overall)
    score_path.chmod(0o444)
    report_path = rerun_root / "overall-report.md"
    write_text_immutable(report_path, _overall_report(overall))
    report_path.chmod(0o444)
    chronology = {
        "schema_version": "typed-extractor-fresh-v3-v4pro-qualification-chronology-v1",
        "status": "frozen",
        "evaluation_id": EVALUATION_ID,
        "qualification_time": overall["qualification_time"],
        "conclusion": overall["status"],
        "requested_model": REQUESTED_MODEL,
        "original_fact_commit": ORIGINAL_FACT_COMMIT,
        "original_bindings": dict(ORIGINAL_BINDINGS),
        "proposal_receipt_sha256": receipts,
        "score_sha256": scores,
        "qualification_sha256": qualifications,
        "overall_score_sha256": sha256_file(score_path),
        "automatic_write_counts": dict(authoring.AUTOMATIC_WRITE_COUNTS),
        "sequence": [
            "proposal_freezes_validated",
            "scores_frozen",
            "layer_qualifications_frozen",
            "overall_conclusion_frozen",
        ],
    }
    path = rerun_root / "qualification-chronology.json"
    write_json_immutable(path, chronology)
    path.chmod(0o444)


def _load_failure(run_root: Path, layer: Layer) -> dict[str, Any]:
    path = run_root / "proposal-freeze-failure-receipt.json"
    content = _read_immutable(path, f"{layer} proposal failure receipt")
    receipt = ProposalFailureReceipt.model_validate_json(content, strict=True)
    if content != canonical_json_bytes(receipt):
        raise ValueError(f"{layer} failure receipt is not canonical JSON")
    return {
        "status": "failed",
        "failure_type": receipt.failure_type,
        "failure_message": receipt.failure_message,
        "request_count": 1,
        "requested_model": REQUESTED_MODEL,
        "receipt_sha256": sha256_file(path),
    }


def score_and_qualify_v4pro_rerun(
    repository_root: Path, workspace_root: Path, qualification_time: str
) -> dict[str, Any]:
    qualification_time = _validate_time(qualification_time)
    _, workspace_root, original_root, rerun_root = _roots(
        repository_root, workspace_root
    )
    if any((rerun_root / name).exists() for name in OVERALL_FILES - {"preflight-receipt.json"}):
        raise ValueError("rerun qualification already exists")
    runs = _discover_runs(rerun_root)
    receipts: dict[str, dict[str, Any]] = {}
    complete = True
    for raw_layer in ("l1", "l2"):
        layer = _require_layer(raw_layer)
        try:
            receipts[layer] = validate_v4pro_proposal_freeze(
                repository_root, workspace_root, layer
            )
        except (FileNotFoundError, ValueError):
            receipts[layer] = _load_failure(runs[layer], layer)
            complete = False
    if not complete:
        overall = {
            "schema_version": "typed-extractor-fresh-v3-v4pro-overall-qualification-v1",
            "status": "incomplete_not_qualified",
            "evaluation_id": EVALUATION_ID,
            "qualification_time": qualification_time,
            "requested_model": REQUESTED_MODEL,
            "layers": receipts,
            "request_counts": {layer: receipts[layer]["request_count"] for layer in ("l1", "l2")},
            "automatic_write_counts": dict(authoring.AUTOMATIC_WRITE_COUNTS),
            "pipeline_integration_authorized": False,
            "authoritative_writes_authorized": False,
        }
        _freeze_overall(
            rerun_root,
            overall,
            {layer: receipts[layer]["receipt_sha256"] for layer in ("l1", "l2")},
            {},
            {},
        )
        return overall

    guard_root = workspace_root / "artifacts/natural-benchmark-slices"
    guard_results = guard_root / "slice-v1/symbolic-fallback-answerability-v2-fastembed-results.json"
    qualifications: dict[str, dict[str, Any]] = {}
    for raw_layer in ("l1", "l2"):
        layer = _require_layer(raw_layer)
        run_root = runs[layer]
        common = {
            "guard_root": guard_root,
            "guard_slice_id": "slice-v1",
            "guard_results_path": guard_results,
            "score_path": run_root / "score.json",
            "report_path": run_root / "report.md",
            "error_analysis_path": run_root / "error-analysis.json",
        }
        if layer == "l1":
            score = run_l1_scoring_file(
                original_root / layer,
                run_root / "proposals.json",
                run_root / "provenance.json",
                manifest_output_names=V3_L1_OUTPUTS,
                **common,
            )
        else:
            score = run_l2_scoring_file(
                original_root / layer,
                run_root / "proposals.json",
                run_root / "provenance.json",
                manifest_output_names=V3_L2_OUTPUTS,
                required_thresholds=V3_L2_THRESHOLDS,
                **common,
            )
        qualification = build_layer_qualification(
            layer,
            score,
            receipts[layer],
            sha256_file(run_root / "score.json"),
        )
        path = run_root / "qualification.json"
        write_json_immutable(path, qualification)
        path.chmod(0o444)
        qualifications[layer] = qualification
    status = (
        "qualified"
        if all(item["layer_ready"] for item in qualifications.values())
        else "not_qualified"
    )
    overall = {
        "schema_version": "typed-extractor-fresh-v3-v4pro-overall-qualification-v1",
        "status": status,
        "evaluation_id": EVALUATION_ID,
        "qualification_time": qualification_time,
        "requested_model": REQUESTED_MODEL,
        "layers": qualifications,
        "request_counts": {"l1": 1, "l2": 1},
        "automatic_write_counts": dict(authoring.AUTOMATIC_WRITE_COUNTS),
        "pipeline_integration_authorized": False,
        "authoritative_writes_authorized": False,
    }
    _freeze_overall(
        rerun_root,
        overall,
        {layer: receipts[layer]["receipt_sha256"] for layer in ("l1", "l2")},
        {layer: sha256_file(runs[layer] / "score.json") for layer in ("l1", "l2")},
        {layer: sha256_file(runs[layer] / "qualification.json") for layer in ("l1", "l2")},
    )
    return overall


def validate_v4pro_rerun(
    repository_root: Path, workspace_root: Path
) -> dict[str, Any]:
    _, _, _, rerun_root = _roots(repository_root, workspace_root)
    overall_path = rerun_root / "overall-score.json"
    overall_content = _read_immutable(overall_path, "rerun overall score")
    overall = json.loads(overall_content)
    if overall_content != canonical_json_bytes(overall):
        raise ValueError("rerun overall score is not canonical JSON")
    chronology_content = _read_immutable(
        rerun_root / "qualification-chronology.json", "rerun chronology"
    )
    chronology = json.loads(chronology_content)
    if chronology_content != canonical_json_bytes(chronology):
        raise ValueError("rerun chronology is not canonical JSON")
    if (
        chronology["conclusion"] != overall["status"]
        or chronology["overall_score_sha256"] != sha256_file(overall_path)
        or chronology["original_bindings"] != ORIGINAL_BINDINGS
        or overall["requested_model"] != REQUESTED_MODEL
    ):
        raise ValueError("rerun chronology drift")
    _read_immutable(rerun_root / "overall-report.md", "rerun overall report")
    if overall["status"] != "incomplete_not_qualified":
        for raw_layer in ("l1", "l2"):
            layer = _require_layer(raw_layer)
            result = validate_v4pro_proposal_freeze(
                repository_root, workspace_root, layer
            )
            run_root = Path(result["run_root"])
            if {path.name for path in run_root.iterdir()} != POST_SCORE_FILES:
                raise ValueError(f"{layer} post-score artifact set mismatch")
            for name in ("score.json", "error-analysis.json", "report.md", "qualification.json"):
                _read_immutable(run_root / name, f"{layer} {name}")
            if chronology["score_sha256"][layer] != sha256_file(run_root / "score.json"):
                raise ValueError(f"{layer} score binding drift")
    return {
        "status": overall["status"],
        "qualification_time": overall["qualification_time"],
        "overall_score_sha256": sha256_file(overall_path),
        "chronology_sha256": sha256_file(rerun_root / "qualification-chronology.json"),
        "layers": overall["layers"],
    }
