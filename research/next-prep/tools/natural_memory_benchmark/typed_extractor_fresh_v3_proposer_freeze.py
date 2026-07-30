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
from . import typed_extractor_fresh_v3_snapshot_receipt as relocation
from .io import canonical_json_bytes, load_json, sha256_file, write_json_immutable
from .typed_extractor_fresh_v3_materialization import (
    FreshV3MaterializationReceipt,
)
from .typed_extractor_l1_api_run import run_l1_openai_compatible_proposer
from .typed_extractor_l2_api_run import run_l2_openai_compatible_proposer
from .typed_extractor_model_run import (
    L1ModelDispatch,
    L1ModelProvenance,
    _validate_dispatch as _validate_l1_dispatch,
    _validate_proposals as _validate_l1_proposals,
    extract_l1_proposal_payload,
    freeze_l1_model_proposals,
    write_l1_model_dispatch,
)
from .typed_extractor_l2_model_run import (
    L2ModelDispatch,
    L2ModelProvenance,
    _validate_dispatch as _validate_l2_dispatch,
    _validate_proposals as _validate_l2_proposals,
    extract_l2_proposal_payload,
    freeze_l2_model_proposals,
    write_l2_model_dispatch,
)
from .typed_extractor_l1 import L1ProposalPayload, L1PublicPayload
from .typed_extractor_l2 import L2ProposalPayload, L2PublicPayload


Layer = Literal["l1", "l2"]

EVALUATION_ID = "typed-extractor-v3-fresh-hidden-v1"
MATERIALIZATION_COMMIT = "703b990a883a0c1e28c2688949beb3b22c97ae65"
MATERIALIZATION_CHRONOLOGY_SHA256 = (
    "fe3cfbd739de477d99089c4ed6f85322236e00deb9b405596f038366bee16cca"
)
ACTIVE_AUTHORING_RECEIPT_SHA256 = (
    "c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c"
)
REQUESTED_MODEL = "deepseek-chat"
ISOLATION_CONTEXT = "fresh-agent-no-history-declarative"
PROPOSER_ID = "deepseek-official-api"
PROPOSER_VERSIONS = {
    "l1": "deepseek-chat@official-api-2026-07-30-fresh-v3-l1",
    "l2": "deepseek-chat@official-api-2026-07-30-fresh-v3-l2",
}
PROMPT_PATHS = {
    "l1": (
        "artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l1-dev-v1/"
        "model-runs/run-20260729T042500Z-deepseek-chat-official-typed-l1-"
        "taxonomy-repair-v1/proposer-prompt-l1.md"
    ),
    "l2": (
        "artifacts/automatic-extraction-assessment/typed-extractor-taxonomy-l2-dev-v1/"
        "model-runs/run-20260729T041501Z-deepseek-chat-official-typed-l2-"
        "taxonomy-baseline-v1/proposer-prompt-l2.md"
    ),
}
PROMPT_SHA256 = {
    "l1": "a5250a453863f3cfd388613d6633d8a529485a11c5226d2965c8235a9c1dc342",
    "l2": "d547a7d8b61eea33735bce4b3c96bb34466bb0fa6eb95d4e1b9070d64f211c6a",
}
PUBLIC_SHA256 = {
    "l1": "d3cf87588f4c2d70a2420ffc5a961c4e1a3cc3beeb9d5222af7b5d6c256a9159",
    "l2": "9f0fe37d410c9f121d9064f49caaa6dda2dd365fb6acae29214ca484c221e160",
}
CASE_COUNTS = {"l1": 24, "l2": 18}

IMPLEMENTATION_PATHS = {
    "typed_extractor_l1.py": "tools/natural_memory_benchmark/typed_extractor_l1.py",
    "test_typed_extractor_l1.py": (
        "tests/natural_memory_benchmark/test_typed_extractor_l1.py"
    ),
    "typed_extractor_l2.py": "tools/natural_memory_benchmark/typed_extractor_l2.py",
    "test_typed_extractor_l2.py": (
        "tests/natural_memory_benchmark/test_typed_extractor_l2.py"
    ),
    "typed_extractor_fresh_v3_proposer_freeze.py": (
        "tools/natural_memory_benchmark/typed_extractor_fresh_v3_proposer_freeze.py"
    ),
    "test_typed_extractor_fresh_v3_proposer_freeze.py": (
        "tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_proposer_freeze.py"
    ),
    "typed_extractor_fresh_v3_qualification.py": (
        "tools/natural_memory_benchmark/typed_extractor_fresh_v3_qualification.py"
    ),
    "test_typed_extractor_fresh_v3_qualification.py": (
        "tests/natural_memory_benchmark/test_typed_extractor_fresh_v3_qualification.py"
    ),
}

PARALLEL_SHA256 = {
    "artifacts/ontology-linking-assessment/dev-v1/assessment.json": (
        "28a76657306d13a65bbfbffcd30d38808fec4d459801e2193085053688480073"
    ),
    "artifacts/ontology-linking-assessment/dev-v1/manifest.json": (
        "070cee82cd9502fab4e6b6cb015039f06f539c86b64b75ccf49e5797cc27f341"
    ),
    "tools/natural_memory_benchmark/l1_admission.py": (
        "c8542b8214fccbac2dca6d1ba59c993055ae2de4e65fec427ba395fd11a77a22"
    ),
    "tools/natural_memory_benchmark/l1_ontology_linking.py": (
        "053e48bf836dbfeb89498dc9b0c64e16e81516e2851b6f3bf95d0fdc1a967321"
    ),
    "tests/natural_memory_benchmark/test_l1_admission.py": (
        "cc0e671c8c808b153f42469a8da72e3f1c47f2c8c26f2ee07d588b74549a48d6"
    ),
    "tests/natural_memory_benchmark/test_l1_ontology_linking.py": (
        "c71a38a637b339cbeb62cf15d1f786d73112722b1856adced75cff8a04e1652b"
    ),
    "docs/designs/2026-07-29-query-compiler-fresh-hidden-preregistration-design.md": (
        "e151e50fba400c3dd26211855572416cdaef69cdc280f361447a13f886d87c7f"
    ),
    "docs/plans/2026-07-29-query-compiler-fresh-hidden-preregistration-plan.md": (
        "a562f12f1a43e59aeeed932fcc14bd220ae2ece193715d5d48e831ba3411bf5c"
    ),
    "tools/natural_memory_benchmark/query_compiler_v2_execution_eval.py": (
        "a4fe7c803a89f3767019a464a9285f5ef143b7d868f7300562ae09f3f198db87"
    ),
    "tools/natural_memory_benchmark/query_compiler_v2_git_fixture.py": (
        "116ea2c829f2ea452cfe6322515b3cf68ef2fa97a921fcb57b3526e56ee92850"
    ),
    "tests/natural_memory_benchmark/test_query_compiler_v2_execution_eval.py": (
        "af8799a6fe5cb4a92e6b1646a7a6acb7828931f14787f8088fa59ad52047a487"
    ),
    "tests/natural_memory_benchmark/test_query_compiler_v2_git_fixture.py": (
        "296cdf59f03c22fa7f6f33db8cd83f766641a6287f88effc92b638df7a8775ec"
    ),
}

BASE_LAYER_FILES = {
    "l1": {
        "authority-l1.json",
        "gold-l1.json",
        "manifest-l1.json",
        "public-l1.json",
        "source-cases-l1.json",
    },
    "l2": {
        "authority-l2.json",
        "gold-l2.json",
        "manifest-l2.json",
        "public-l2.json",
        "source-cases-l2.json",
    },
}
SUCCESS_FILES = {
    "dispatch.json",
    "raw-response.json",
    "proposals.json",
    "provenance.json",
    "proposal-freeze-receipt.json",
}
ARTIFACT_FILES = (
    "dispatch.json",
    "raw-response.json",
    "proposals.json",
    "provenance.json",
)


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FrozenArtifact(StrictModel):
    filename: str = Field(pattern=r"^[^/\\]+$")
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(ge=1)
    mode: Literal["0444"] = "0444"


class FreshV3ProposalFreezeReceipt(StrictModel):
    schema_version: Literal["typed-extractor-fresh-v3-proposal-freeze-v1"] = (
        "typed-extractor-fresh-v3-proposal-freeze-v1"
    )
    status: Literal["frozen"] = "frozen"
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    layer: Layer
    dataset_id: str = Field(min_length=1)
    case_count: int = Field(ge=1)
    run_id: str = Field(min_length=1)
    request_ordinal: Literal[1] = 1
    request_count: Literal[1] = 1
    requested_model: Literal["deepseek-chat"] = REQUESTED_MODEL
    response_model: str = Field(min_length=1)
    isolation_context: Literal["fresh-agent-no-history-declarative"] = (
        ISOLATION_CONTEXT
    )
    history_context_inherited: Literal[False] = False
    authority_or_gold_read_before_freeze: Literal[False] = False
    allowed_files: dict[str, str]
    prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    public_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    materialization_commit: Literal[
        "703b990a883a0c1e28c2688949beb3b22c97ae65"
    ] = MATERIALIZATION_COMMIT
    materialization_chronology_sha256: Literal[
        "fe3cfbd739de477d99089c4ed6f85322236e00deb9b405596f038366bee16cca"
    ] = MATERIALIZATION_CHRONOLOGY_SHA256
    active_authoring_receipt_sha256: Literal[
        "c810f421d5a3b0726b862ec2f12c89e0d638e0747892637e2a32977587b7ef8c"
    ] = ACTIVE_AUTHORING_RECEIPT_SHA256
    preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    parallel_sha256: dict[str, str]
    automatic_write_counts: dict[str, int]
    artifacts: dict[str, FrozenArtifact]
    freeze_sequence: tuple[
        Literal["dispatch"],
        Literal["raw_response"],
        Literal["proposals"],
        Literal["provenance"],
    ] = ("dispatch", "raw_response", "proposals", "provenance")

    @model_validator(mode="after")
    def validate_exact_contract(self) -> "FreshV3ProposalFreezeReceipt":
        if self.case_count != CASE_COUNTS[self.layer]:
            raise ValueError("proposal receipt case count mismatch")
        if self.prompt_sha256 != PROMPT_SHA256[self.layer]:
            raise ValueError("proposal receipt prompt hash mismatch")
        if self.public_sha256 != PUBLIC_SHA256[self.layer]:
            raise ValueError("proposal receipt public hash mismatch")
        if set(self.artifacts) != set(ARTIFACT_FILES):
            raise ValueError("proposal receipt artifact registry mismatch")
        if self.automatic_write_counts != authoring.AUTOMATIC_WRITE_COUNTS:
            raise ValueError("proposal receipt write boundary mismatch")
        return self


class FreshV3ProposalFailureReceipt(StrictModel):
    schema_version: Literal["typed-extractor-fresh-v3-proposal-failure-v1"] = (
        "typed-extractor-fresh-v3-proposal-failure-v1"
    )
    status: Literal["frozen_failure"] = "frozen_failure"
    evaluation_id: Literal["typed-extractor-v3-fresh-hidden-v1"] = EVALUATION_ID
    layer: Layer
    run_id: str = Field(min_length=1)
    request_ordinal: Literal[1] = 1
    request_count: Literal[1] = 1
    requested_model: Literal["deepseek-chat"] = REQUESTED_MODEL
    failure_type: str = Field(min_length=1)
    failure_message: str = Field(min_length=1)
    retry_performed: Literal[False] = False
    fallback_model_used: Literal[False] = False
    preflight_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    implementation_sha256: dict[str, str]
    parallel_sha256: dict[str, str]
    artifacts: dict[str, FrozenArtifact]


def _require_layer(layer: str) -> Layer:
    if layer not in ("l1", "l2"):
        raise ValueError("layer must be l1 or l2")
    return layer


def _run_ids(run_label: str) -> dict[str, str]:
    try:
        parsed = datetime.strptime(run_label, "%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError) as error:
        raise ValueError("invalid run label") from error
    if parsed.strftime("%Y%m%dT%H%M%SZ") != run_label:
        raise ValueError("invalid run label")
    return {
        "l1": f"run-{run_label}-deepseek-chat-official-typed-l1-fresh-hidden-v3",
        "l2": f"run-{run_label}-deepseek-chat-official-typed-l2-fresh-hidden-v3",
    }


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _roots(repository_root: Path, workspace_root: Path) -> tuple[Path, Path, Path]:
    repository_root = relocation._require_repository_root(repository_root)
    workspace_root = relocation._require_workspace_root(repository_root, workspace_root)
    evaluation_root = repository_root / relocation.NORMALIZED_EVALUATION_ROOT
    return repository_root, workspace_root, evaluation_root


def _run_git(repository_root: Path, *args: str) -> bytes:
    completed = subprocess.run(
        ["git", "-C", str(repository_root), *args],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(errors="replace").strip()
        raise ValueError(f"Git command failed: {' '.join(args)}: {detail}")
    return completed.stdout


def _require_directory(path: Path, label: str, mode: int = 0o775) -> None:
    opened = path.lstat()
    if not stat.S_ISDIR(opened.st_mode) or stat.S_ISLNK(opened.st_mode):
        raise ValueError(f"{label} must be a non-symlink directory")
    if stat.S_IMODE(opened.st_mode) != mode:
        raise ValueError(f"{label} mode drift")


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


def _read_regular(path: Path, label: str) -> bytes:
    opened = path.lstat()
    if not stat.S_ISREG(opened.st_mode) or stat.S_ISLNK(opened.st_mode):
        raise ValueError(f"{label} must be a regular non-symlink file")
    content = path.read_bytes()
    rechecked = path.lstat()
    if (opened.st_dev, opened.st_ino, opened.st_size) != (
        rechecked.st_dev,
        rechecked.st_ino,
        rechecked.st_size,
    ):
        raise ValueError(f"{label} changed while reading")
    return content


def _require_absent(path: Path, label: str) -> None:
    try:
        path.lstat()
    except FileNotFoundError:
        return
    raise ValueError(f"{label} must be absent")


def _sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _implementation_git_bindings(
    repository_root: Path,
    workspace_root: Path,
) -> dict[str, str]:
    bindings: dict[str, str] = {}
    for name, workspace_relative in IMPLEMENTATION_PATHS.items():
        repository_relative = f"research/next-prep/{workspace_relative}"
        committed = _run_git(repository_root, "show", f"HEAD:{repository_relative}")
        current = _read_regular(workspace_root / workspace_relative, name)
        if current != committed:
            raise ValueError(f"committed implementation bytes drift: {name}")
        bindings[name] = _sha256_bytes(committed)
    return bindings


def _parallel_bindings(workspace_root: Path) -> dict[str, str]:
    for relative, expected in PARALLEL_SHA256.items():
        path = workspace_root / relative
        opened = path.lstat()
        if not stat.S_ISREG(opened.st_mode) or stat.S_ISLNK(opened.st_mode):
            raise ValueError(f"parallel path must be a regular file: {relative}")
        if sha256_file(path) != expected:
            raise ValueError(f"parallel session hash drift: {relative}")
    return dict(PARALLEL_SHA256)


def _require_git_state(repository_root: Path) -> str:
    _run_git(repository_root, "diff", "--cached", "--quiet")
    status = _run_git(
        repository_root,
        "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
    ).decode("utf-8")
    dirty_paths = {
        entry[3:]
        for entry in status.split("\0")
        if entry and len(entry) >= 4
    }
    allowed = {f"research/next-prep/{path}" for path in PARALLEL_SHA256}
    formal_prefix = (
        "research/next-prep/artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-v1/"
    )
    unexpected = {
        path
        for path in dirty_paths - allowed
        if not path.startswith(formal_prefix)
    }
    if unexpected:
        raise ValueError(f"unexpected dirty paths: {sorted(unexpected)}")
    _run_git(
        repository_root,
        "merge-base",
        "--is-ancestor",
        MATERIALIZATION_COMMIT,
        "HEAD",
    )
    return _run_git(repository_root, "rev-parse", "HEAD").decode("ascii").strip()


def _validate_base_materialization(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
    *,
    allow_model_runs: bool,
) -> dict[str, Any]:
    del repository_root
    _require_directory(evaluation_root, "fresh v3 evaluation root")
    chronology_path = evaluation_root / "chronology-receipt.json"
    chronology_bytes = _read_immutable(chronology_path, "materialization chronology")
    if _sha256_bytes(chronology_bytes) != MATERIALIZATION_CHRONOLOGY_SHA256:
        raise ValueError("materialization chronology hash drift")
    chronology = FreshV3MaterializationReceipt.model_validate(
        json.loads(chronology_bytes),
        strict=True,
    )
    if chronology_bytes != canonical_json_bytes(chronology):
        raise ValueError("materialization chronology is not canonical JSON")
    active_path = (
        workspace_root
        / "artifacts/automatic-extraction-assessment/"
        "typed-extractor-v3-fresh-hidden-prereg-v1/authoring-implementation-receipt.json"
    )
    if _sha256_bytes(_read_immutable(active_path, "active authoring receipt")) != (
        ACTIVE_AUTHORING_RECEIPT_SHA256
    ):
        raise ValueError("active authoring receipt hash drift")
    for layer in ("l1", "l2"):
        layer_root = evaluation_root / layer
        _require_directory(layer_root, f"{layer} materialization root")
        expected_entries = set(BASE_LAYER_FILES[layer])
        if allow_model_runs:
            expected_entries.add("model-runs")
        entries = {path.name for path in layer_root.iterdir()}
        if entries != expected_entries:
            raise ValueError(f"unexpected {layer} materialization entries: {sorted(entries)}")
        for name, binding in chronology.layers[layer].items():
            path = layer_root / name
            content = _read_immutable(path, f"materialized {layer}/{name}")
            if (
                _sha256_bytes(content) != binding.sha256
                or len(content) != binding.size_bytes
                or binding.mode != "0444"
            ):
                raise ValueError(f"materialized payload drift: {layer}/{name}")
    if (
        chronology.automatic_write_counts.model_dump(mode="json")
        != authoring.AUTOMATIC_WRITE_COUNTS
    ):
        raise ValueError("automatic write counts drift")
    return chronology.model_dump(mode="json")


def _validate_prompts_and_public(
    workspace_root: Path,
    evaluation_root: Path,
) -> dict[str, dict[str, str]]:
    result: dict[str, dict[str, str]] = {}
    for layer in ("l1", "l2"):
        prompt = workspace_root / PROMPT_PATHS[layer]
        public = evaluation_root / layer / f"public-{layer}.json"
        if _sha256_bytes(_read_immutable(prompt, f"{layer} proposer prompt")) != (
            PROMPT_SHA256[layer]
        ):
            raise ValueError(f"{layer} proposer prompt hash drift")
        if _sha256_bytes(_read_immutable(public, f"{layer} public input")) != (
            PUBLIC_SHA256[layer]
        ):
            raise ValueError(f"{layer} public input hash drift")
        result[layer] = {
            "prompt_sha256": PROMPT_SHA256[layer],
            "public_sha256": PUBLIC_SHA256[layer],
        }
    return result


def _require_no_result_paths(evaluation_root: Path, *, before_dispatch: bool) -> None:
    for name in (
        "overall-score.json",
        "overall-report.md",
        "qualification-chronology.json",
    ):
        _require_absent(evaluation_root / name, name)
    for layer in ("l1", "l2"):
        layer_root = evaluation_root / layer
        if before_dispatch:
            _require_absent(layer_root / "model-runs", f"{layer} model-runs")
        for path in evaluation_root.rglob("*"):
            if "staging" in path.name or path.name.endswith(".tmp"):
                raise ValueError(f"stale staging path exists: {path}")


def _common_bindings(
    repository_root: Path,
    workspace_root: Path,
    evaluation_root: Path,
    *,
    allow_model_runs: bool,
) -> dict[str, Any]:
    materialization = _validate_base_materialization(
        repository_root,
        workspace_root,
        evaluation_root,
        allow_model_runs=allow_model_runs,
    )
    prompts = _validate_prompts_and_public(workspace_root, evaluation_root)
    protected = authoring._protected_state(workspace_root)
    head = _require_git_state(repository_root)
    implementation = _implementation_git_bindings(repository_root, workspace_root)
    parallel = _parallel_bindings(workspace_root)
    result = {
        "status": "valid",
        "head": head,
        "materialization_commit": MATERIALIZATION_COMMIT,
        "materialization_chronology_sha256": MATERIALIZATION_CHRONOLOGY_SHA256,
        "active_authoring_receipt_sha256": ACTIVE_AUTHORING_RECEIPT_SHA256,
        "materialization": materialization,
        "prompts_and_public": prompts,
        "implementation_sha256": implementation,
        "parallel_sha256": parallel,
        "candidate_v3_queue_sha256": authoring.CANDIDATE_QUEUE_SHA256,
        "guard_fingerprint": authoring.GUARD_FINGERPRINT,
        "guard_results_sha256": protected["guard_results_sha256"],
        "guard_counts": protected["guard_counts"],
        "automatic_write_counts": dict(authoring.AUTOMATIC_WRITE_COUNTS),
        "manual_identity_adjudications_materialized": False,
        "embedding_authority": False,
        "longmemeval_status": "structured_l2_identity_unresolved",
    }
    result["preflight_sha256"] = _sha256_bytes(canonical_json_bytes(result))
    return result


def validate_fresh_v3_proposer_preflight(
    repository_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    repository_root, workspace_root, evaluation_root = _roots(
        repository_root,
        workspace_root,
    )
    _require_no_result_paths(evaluation_root, before_dispatch=True)
    result = _common_bindings(
        repository_root,
        workspace_root,
        evaluation_root,
        allow_model_runs=False,
    )
    result["preflight_sha256"] = _sha256_bytes(canonical_json_bytes(result))
    return result


def _validate_proposer_state(
    repository_root: Path,
    workspace_root: Path,
) -> dict[str, Any]:
    repository_root, workspace_root, evaluation_root = _roots(
        repository_root,
        workspace_root,
    )
    _require_no_result_paths(evaluation_root, before_dispatch=False)
    return _common_bindings(
        repository_root,
        workspace_root,
        evaluation_root,
        allow_model_runs=True,
    )


def _dispatch_paths(
    workspace_root: Path,
    evaluation_root: Path,
    layer: Layer,
    run_id: str,
) -> tuple[Path, Path, Path]:
    public = evaluation_root / layer / f"public-{layer}.json"
    prompt = workspace_root / PROMPT_PATHS[layer]
    run_root = evaluation_root / layer / "model-runs" / run_id
    return public, prompt, run_root


def _validate_dispatch_file(
    workspace_root: Path,
    evaluation_root: Path,
    layer: Layer,
    run_root: Path,
) -> dict[str, Any]:
    dispatch_path = run_root / "dispatch.json"
    dispatch_bytes = _read_immutable(dispatch_path, f"{layer} dispatch")
    public = evaluation_root / layer / f"public-{layer}.json"
    prompt = workspace_root / PROMPT_PATHS[layer]
    if layer == "l1":
        dispatch = L1ModelDispatch.model_validate(json.loads(dispatch_bytes), strict=True)
        _validate_l1_dispatch(
            dispatch,
            public_path=public,
            prompt_path=prompt,
            isolation_context=ISOLATION_CONTEXT,
        )
    else:
        dispatch = L2ModelDispatch.model_validate(json.loads(dispatch_bytes), strict=True)
        _validate_l2_dispatch(
            dispatch,
            public_path=public,
            prompt_path=prompt,
            isolation_context=ISOLATION_CONTEXT,
        )
    if dispatch_bytes != canonical_json_bytes(dispatch):
        raise ValueError(f"{layer} dispatch is not canonical JSON")
    if dispatch.requested_model != REQUESTED_MODEL:
        raise ValueError(f"{layer} requested model drift")
    if dispatch.authority_or_gold_allowed is not False:
        raise ValueError(f"{layer} dispatch allows authority or gold")
    serialized_allowed = json.dumps(dispatch.allowed_files, sort_keys=True).lower()
    if "authority" in serialized_allowed or "gold" in serialized_allowed:
        raise ValueError(f"{layer} dispatch exposes authority or gold")
    return dispatch.model_dump(mode="json")


def freeze_fresh_v3_dispatches(
    repository_root: Path,
    workspace_root: Path,
    run_label: str,
) -> dict[str, Any]:
    repository_root, workspace_root, evaluation_root = _roots(
        repository_root,
        workspace_root,
    )
    run_ids = _run_ids(run_label)
    preflight = validate_fresh_v3_proposer_preflight(
        repository_root,
        workspace_root,
    )
    for layer in ("l1", "l2"):
        public, prompt, run_root = _dispatch_paths(
            workspace_root,
            evaluation_root,
            layer,
            run_ids[layer],
        )
        model_runs = run_root.parent
        model_runs.mkdir(mode=0o775)
        model_runs.chmod(0o775)
        run_root.mkdir(mode=0o775)
        run_root.chmod(0o775)
        if layer == "l1":
            write_l1_model_dispatch(
                public,
                prompt,
                run_root / "dispatch.json",
                run_id=run_ids[layer],
                proposer_id=PROPOSER_ID,
                proposer_version=PROPOSER_VERSIONS[layer],
                requested_model=REQUESTED_MODEL,
                isolation_context=ISOLATION_CONTEXT,
            )
        else:
            write_l2_model_dispatch(
                public,
                prompt,
                run_root / "dispatch.json",
                run_id=run_ids[layer],
                proposer_id=PROPOSER_ID,
                proposer_version=PROPOSER_VERSIONS[layer],
                requested_model=REQUESTED_MODEL,
                isolation_context=ISOLATION_CONTEXT,
            )
    dispatches: dict[str, Any] = {}
    for layer in ("l1", "l2"):
        _, _, run_root = _dispatch_paths(
            workspace_root,
            evaluation_root,
            layer,
            run_ids[layer],
        )
        dispatches[layer] = _validate_dispatch_file(
            workspace_root,
            evaluation_root,
            layer,
            run_root,
        )
    return {
        "status": "dispatches_frozen",
        "run_ids": run_ids,
        "preflight_sha256": preflight["preflight_sha256"],
        "dispatch_sha256": {
            layer: sha256_file(
                evaluation_root
                / layer
                / "model-runs"
                / run_ids[layer]
                / "dispatch.json"
            )
            for layer in ("l1", "l2")
        },
        "dispatches": dispatches,
    }


def _discover_run_roots(evaluation_root: Path) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for layer in ("l1", "l2"):
        model_runs = evaluation_root / layer / "model-runs"
        _require_directory(model_runs, f"{layer} model-runs")
        children = list(model_runs.iterdir())
        if len(children) != 1:
            raise ValueError(f"{layer} must contain exactly one formal run")
        _require_directory(children[0], f"{layer} formal run")
        result[layer] = children[0]
    return result


def _require_both_dispatches(
    workspace_root: Path,
    evaluation_root: Path,
) -> dict[str, Path]:
    runs = _discover_run_roots(evaluation_root)
    for layer in ("l1", "l2"):
        dispatch = _validate_dispatch_file(
            workspace_root,
            evaluation_root,
            layer,
            runs[layer],
        )
        if dispatch["run_id"] != runs[layer].name:
            raise ValueError(f"{layer} dispatch run path mismatch")
    return runs


def _artifact(path: Path) -> FrozenArtifact:
    content = _read_immutable(path, path.name)
    return FrozenArtifact(
        filename=path.name,
        sha256=_sha256_bytes(content),
        size_bytes=len(content),
    )


def _failure_receipt(
    run_root: Path,
    layer: Layer,
    state: dict[str, Any],
    error: Exception,
) -> None:
    artifacts = {
        name: _artifact(run_root / name)
        for name in ARTIFACT_FILES
        if (run_root / name).is_file()
    }
    receipt = FreshV3ProposalFailureReceipt(
        layer=layer,
        run_id=run_root.name,
        failure_type=type(error).__name__,
        failure_message=str(error) or type(error).__name__,
        preflight_sha256=state["preflight_sha256"],
        implementation_sha256=state["implementation_sha256"],
        parallel_sha256=state["parallel_sha256"],
        artifacts=artifacts,
    )
    path = run_root / "proposal-freeze-failure-receipt.json"
    write_json_immutable(path, receipt)
    path.chmod(0o444)


def _build_success_receipt(
    run_root: Path,
    layer: Layer,
    state: dict[str, Any],
) -> FreshV3ProposalFreezeReceipt:
    raw = load_json(run_root / "raw-response.json")
    response_model = raw.get("model")
    if not isinstance(response_model, str) or not response_model:
        raise ValueError("raw response model missing")
    dispatch = load_json(run_root / "dispatch.json")
    return FreshV3ProposalFreezeReceipt(
        layer=layer,
        dataset_id=dispatch["dataset_id"],
        case_count=dispatch["case_count"],
        run_id=dispatch["run_id"],
        response_model=response_model,
        allowed_files=dispatch["allowed_files"],
        prompt_sha256=PROMPT_SHA256[layer],
        public_sha256=PUBLIC_SHA256[layer],
        preflight_sha256=state["preflight_sha256"],
        implementation_sha256=state["implementation_sha256"],
        parallel_sha256=state["parallel_sha256"],
        automatic_write_counts=dict(authoring.AUTOMATIC_WRITE_COUNTS),
        artifacts={name: _artifact(run_root / name) for name in ARTIFACT_FILES},
    )


def run_and_freeze_fresh_v3_layer(
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
        raise ValueError("timeout_seconds must be a positive integer")
    repository_root, workspace_root, evaluation_root = _roots(
        repository_root,
        workspace_root,
    )
    state = _validate_proposer_state(repository_root, workspace_root)
    runs = _require_both_dispatches(workspace_root, evaluation_root)
    run_root = runs[layer]
    if {path.name for path in run_root.iterdir()} != {"dispatch.json"}:
        raise ValueError(f"{layer} formal run has already been attempted")
    public = evaluation_root / layer / f"public-{layer}.json"
    prompt = workspace_root / PROMPT_PATHS[layer]
    raw_path = run_root / "raw-response.json"
    proposals_path = run_root / "proposals.json"
    provenance_path = run_root / "provenance.json"
    for path in (raw_path, proposals_path, provenance_path):
        _require_absent(path, path.name)
    try:
        with tempfile.TemporaryDirectory(
            prefix=f"ke-memory-fresh-v3-{layer}-proposals-"
        ) as temporary:
            staged = Path(temporary) / "parsed-proposals.json"
            if layer == "l1":
                run_l1_openai_compatible_proposer(
                    public_path=public,
                    prompt_path=prompt,
                    dispatch_path=run_root / "dispatch.json",
                    raw_response_path=raw_path,
                    staged_proposals_path=staged,
                    base_url=base_url,
                    api_key=api_key,
                    model=REQUESTED_MODEL,
                    timeout_seconds=timeout_seconds,
                    opener=opener,
                )
                freeze_l1_model_proposals(
                    public,
                    staged,
                    proposals_path,
                    provenance_path,
                    prompt_path=prompt,
                    dispatch_path=run_root / "dispatch.json",
                    raw_response_path=raw_path,
                    isolation_context=ISOLATION_CONTEXT,
                )
            else:
                run_l2_openai_compatible_proposer(
                    public_path=public,
                    prompt_path=prompt,
                    dispatch_path=run_root / "dispatch.json",
                    raw_response_path=raw_path,
                    staged_proposals_path=staged,
                    base_url=base_url,
                    api_key=api_key,
                    model=REQUESTED_MODEL,
                    timeout_seconds=timeout_seconds,
                    opener=opener,
                )
                freeze_l2_model_proposals(
                    public,
                    staged,
                    proposals_path,
                    provenance_path,
                    prompt_path=prompt,
                    dispatch_path=run_root / "dispatch.json",
                    raw_response_path=raw_path,
                    isolation_context=ISOLATION_CONTEXT,
                )
        receipt = _build_success_receipt(run_root, layer, state)
        receipt_path = run_root / "proposal-freeze-receipt.json"
        write_json_immutable(receipt_path, receipt)
        receipt_path.chmod(0o444)
    except Exception as error:
        try:
            _failure_receipt(run_root, layer, state, error)
        except Exception as receipt_error:
            error.add_note(f"failure receipt could not be frozen: {receipt_error}")
        raise
    result = validate_fresh_v3_proposal_freeze(
        repository_root,
        workspace_root,
        layer,
    )
    return {**result, "run_root": str(run_root), "request_ordinal": 1}


def validate_fresh_v3_proposal_freeze(
    repository_root: Path,
    workspace_root: Path,
    layer: Layer,
) -> dict[str, Any]:
    layer = _require_layer(layer)
    repository_root, workspace_root, evaluation_root = _roots(
        repository_root,
        workspace_root,
    )
    state = _validate_proposer_state(repository_root, workspace_root)
    runs = _require_both_dispatches(workspace_root, evaluation_root)
    run_root = runs[layer]
    if {path.name for path in run_root.iterdir()} != SUCCESS_FILES:
        raise ValueError(f"{layer} proposal freeze artifact set mismatch")
    receipt_path = run_root / "proposal-freeze-receipt.json"
    receipt_bytes = _read_immutable(receipt_path, f"{layer} proposal freeze receipt")
    receipt = FreshV3ProposalFreezeReceipt.model_validate_json(
        receipt_bytes,
        strict=True,
    )
    if receipt_bytes != canonical_json_bytes(receipt):
        raise ValueError(f"{layer} proposal freeze receipt is not canonical JSON")
    dispatch_payload = _validate_dispatch_file(
        workspace_root,
        evaluation_root,
        layer,
        run_root,
    )
    public_path = evaluation_root / layer / f"public-{layer}.json"
    raw_payload = load_json(run_root / "raw-response.json")
    proposals_payload = load_json(run_root / "proposals.json")
    if layer == "l1":
        public = L1PublicPayload.model_validate(load_json(public_path), strict=True)
        dispatch = L1ModelDispatch.model_validate(dispatch_payload, strict=True)
        proposals = L1ProposalPayload.model_validate(proposals_payload, strict=True)
        provenance = L1ModelProvenance.model_validate_json(
            (run_root / "provenance.json").read_bytes(),
            strict=True,
        )
        if extract_l1_proposal_payload(raw_payload) != proposals:
            raise ValueError("L1 frozen proposals do not replay from raw response")
        _validate_l1_proposals(public, proposals, dispatch)
    else:
        public = L2PublicPayload.model_validate(load_json(public_path), strict=True)
        dispatch = L2ModelDispatch.model_validate(dispatch_payload, strict=True)
        proposals = L2ProposalPayload.model_validate(proposals_payload, strict=True)
        provenance = L2ModelProvenance.model_validate_json(
            (run_root / "provenance.json").read_bytes(),
            strict=True,
        )
        if extract_l2_proposal_payload(raw_payload) != proposals:
            raise ValueError("L2 frozen proposals do not replay from raw response")
        _validate_l2_proposals(public, proposals, dispatch)
    if (
        provenance.dispatch_sha256 != sha256_file(run_root / "dispatch.json")
        or provenance.raw_response_sha256 != sha256_file(run_root / "raw-response.json")
        or provenance.proposals_sha256 != sha256_file(run_root / "proposals.json")
        or provenance.run_id != dispatch.run_id
        or provenance.allowed_files != dispatch.allowed_files
        or provenance.allowed_input_sha256 != dispatch.allowed_input_sha256
        or provenance.response_model != raw_payload.get("model")
    ):
        raise ValueError(f"{layer} provenance chain drift")
    expected = _build_success_receipt(run_root, layer, state)
    if receipt != expected:
        raise ValueError(f"{layer} proposal freeze receipt drift")
    return {
        "status": "valid",
        "layer": layer,
        "run_id": receipt.run_id,
        "run_root": str(run_root),
        "request_count": receipt.request_count,
        "request_ordinal": receipt.request_ordinal,
        "requested_model": receipt.requested_model,
        "response_model": receipt.response_model,
        "receipt_sha256": _sha256_bytes(receipt_bytes),
        "artifacts": {
            name: binding.model_dump(mode="json")
            for name, binding in receipt.artifacts.items()
        },
    }
