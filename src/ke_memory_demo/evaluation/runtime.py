"""Evaluation-specific runtime wiring.

Split out of ``pipeline/runtime.py``, which had grown to hold both generic pipeline
wiring and the evaluation stage's own preflight, promotion and report plumbing. The
mix made orchestration depend on measurement: ``pipeline`` imported twenty names
from ``evaluation``, so the layer that runs the system could not be loaded or
reasoned about without the layer that scores it.

What stayed behind is the wiring every stage needs -- ``RuntimeFactory``, the git
and probe helpers, the trace plumbing. What moved here is what only the evaluation
stage uses: the frozen dataset expectations, the approved spec and plan digests,
preflight port wiring, and report materialization.

``RuntimeFactory`` deliberately did not move. Three of its twelve methods touch
evaluation and nine do not; splitting the class would fragment the single entry
point every stage shares. Those three methods import from this module lazily
instead, so the class stays whole while the import edge points downward.
"""

from __future__ import annotations

import os
import re
import stat
import subprocess
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

from ke_memory_demo.contracts import (
    EVALUATION_ARTIFACT_REGISTRY,
    PIPELINE_ARTIFACT_REGISTRY,
    PipelineRunManifest,
    PipelineStage,
)
from ke_memory_demo.core.errors import PreflightCheckFailure
from ke_memory_demo.domain.conversation import Conversation
from ke_memory_demo.evaluation.models import EvaluationRun, ReportDocument
from ke_memory_demo.evaluation.preflight import EvaluationPreflight
from ke_memory_demo.evaluation.questions import normalize_questions
from ke_memory_demo.evaluation.report import materialize_report_documents
from ke_memory_demo.infra.llm import StructuredModelClient
from ke_memory_demo.infra.telemetry import InMemoryTraceRecorder, TraceContext
from ke_memory_demo.ontology.elasticsearch import ElasticsearchVocabulary
from ke_memory_demo.pipeline.runtime import (
    _GIT_SHA,
    RuntimeInvariantError,
    _git_text,
    _nonsecret_model_endpoint,
    _read_only_git_env,
    _sha256_file,
    _snapshot_records_from_git,
    probe_state_repository_writable,
)
from ke_memory_demo.settings import (
    AppSettings,
    ConfigLayout,
    load_settings,
    resolve_config_layout,
)
from ke_memory_demo.snapshots import GitSnapshotStore
from ke_memory_demo.storage import ArtifactStore
from ke_memory_demo.storage.layout import StateLayout, validate_storage_name


_SK_CREDENTIAL = re.compile(rb"sk-[A-Za-z0-9_-]{12,}", flags=re.ASCII)
_APPROVED_SPEC_PATH = Path("docs/superpowers/specs/2026-07-17-ke-only-evaluation-design.md")
_APPROVED_SPEC_SHA256 = "192bf8384185eaa014634ea61fee18c2ab35220bd23037c78da959aca8ca73cb"
_APPROVED_PLAN_PATH = Path("docs/superpowers/plans/2026-07-17-ke-only-completion-implementation.md")
_APPROVED_PLAN_SHA256 = "47fcf0e87ee7738a190c8cb3a9d3b253e35f01a446c465d2f47d024c216e680b"
_FIXED_DATASET_SHA256 = "690106a93ab88dac46e8fef1e84884acc889518424240f57a47428d3efbe6346"
_FIXED_DIRECTORIES = (4, 15, 17)
_FIXED_SESSIONS = 13
_FIXED_EXCHANGES = 385
_FIXED_QUESTIONS = 60


class _EvaluationProbeResponse(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ready: Literal[True]


def evaluation_can_promote(run: EvaluationRun, *, smoke: bool) -> bool:
    expected_ids = run.expected_question_ids
    return (
        not smoke
        and run.status.value == "complete"
        and len(expected_ids) == _FIXED_QUESTIONS
        and tuple(item.question_id for item in run.answers) == expected_ids
        and tuple(item.question_id for item in run.judgements) == expected_ids
        and not run.failures
    )


def materialize_evaluation_report(
    state_root: Path,
    run_id: str,
    snapshot_id: str,
) -> tuple[Path, ...]:
    validate_storage_name(run_id, label="run ID")
    artifacts = ArtifactStore(
        state_root,
        registry={
            **PIPELINE_ARTIFACT_REGISTRY,
            **dict(EVALUATION_ARTIFACT_REGISTRY),
        },
    )
    snapshots = GitSnapshotStore.init(artifacts.root, artifacts)
    verified = snapshots.verify(snapshot_id, run_id, PipelineStage.EVALUATION_COMPLETE)
    documents = _snapshot_records_from_git(
        artifacts.root,
        verified.snapshot_id,
        run_id,
        "report_documents",
        ReportDocument,
        stage=PipelineStage.EVALUATION_COMPLETE,
    )
    return materialize_report_documents(
        documents,
        artifacts.root / "exports" / run_id,
        layout=artifacts.layout,
    )


def finalize_evaluation_outputs(
    *,
    run: EvaluationRun,
    smoke: bool,
    state_root: Path,
    run_id: str,
    documents: Sequence[ReportDocument],
    promote_complete: Callable[[], str],
) -> str | None:
    validate_storage_name(run_id, label="run ID")
    validated_run = EvaluationRun.model_validate(run)
    validated_documents = tuple(ReportDocument.model_validate(item) for item in documents)
    if smoke:
        return None
    if not evaluation_can_promote(validated_run, smoke=False):
        layout = StateLayout(state_root)
        materialize_report_documents(
            validated_documents,
            layout.root / "exports" / run_id / "incomplete",
            layout=layout,
        )
        return None
    snapshot_id = promote_complete()
    if _GIT_SHA.fullmatch(snapshot_id) is None:
        raise RuntimeInvariantError("evaluation promotion returned an invalid snapshot ID")
    return snapshot_id


class _LiveEvaluationPreflightPorts:
    def __init__(
        self,
        config_root: Path | ConfigLayout,
        state_root: Path,
        run_id: str,
        snapshot_id: str,
    ) -> None:
        self._config_root = (
            config_root.project_root
            if isinstance(config_root, ConfigLayout)
            else config_root.expanduser()
        )
        self._state_root = state_root.expanduser().resolve()
        self._run_id = run_id
        self._snapshot_id = snapshot_id
        self._dotenv_path = self._config_root / ".env.local"
        self._dotenv_failure: str | None = None
        self._settings: AppSettings | None = None
        self._settings_error = "SettingsUnavailable"
        try:
            layout = (
                config_root
                if isinstance(config_root, ConfigLayout)
                else resolve_config_layout(config_root)
            )
        except Exception as error:
            self._settings_error = type(error).__name__
        else:
            self._config_root = layout.project_root
            self._dotenv_path = layout.project_root / ".env.local"
            self._dotenv_failure = self._dotenv_permission_failure()
            if self._dotenv_failure is None:
                try:
                    self._settings = load_settings(layout)
                except Exception as error:
                    self._settings_error = type(error).__name__
        self._snapshot_cache: tuple[PipelineRunManifest, tuple[Conversation, ...]] | None = None

    async def check(self, name: str) -> str:
        if name == "code_identity":
            return self._check_code_identity()
        if name == "concurrency":
            return self._check_concurrency()
        if name == "credential_scan":
            return self._check_credentials()
        if name == "embedding":
            return self._check_embedding()
        if name == "environment":
            return self._check_environment()
        if name == "judge_model":
            return await self._check_model("judge_model")
        if name == "ke_ready_snapshot":
            return self._check_ke_ready_snapshot()
        if name == "ontology_identity":
            return await self._check_ontology_identity()
        if name == "state_repo":
            return self._check_state_repo()
        if name == "work_model":
            return await self._check_model("work_model")
        raise PreflightCheckFailure(f"{name}:UnknownCheck")

    def _check_code_identity(self) -> str:
        commit = _git_text(self._config_root, "rev-parse", "--verify", "HEAD^{commit}")
        if _GIT_SHA.fullmatch(commit) is None:
            raise PreflightCheckFailure("code_identity:InvalidGitHead")
        if _git_text(
            self._config_root,
            "status",
            "--porcelain=v1",
            "--untracked-files=all",
        ):
            raise PreflightCheckFailure("code_identity:DirtyWorktree")
        spec_sha = _sha256_file(self._config_root / _APPROVED_SPEC_PATH)
        plan_sha = _sha256_file(self._config_root / _APPROVED_PLAN_PATH)
        if spec_sha != _APPROVED_SPEC_SHA256:
            raise PreflightCheckFailure("code_identity:SpecHashMismatch")
        if plan_sha != _APPROVED_PLAN_SHA256:
            raise PreflightCheckFailure("code_identity:PlanHashMismatch")
        return f"code_identity:commit={commit}:spec={spec_sha}:plan={plan_sha}"

    def _check_concurrency(self) -> str:
        settings = self._require_settings("concurrency")
        concurrency = settings.evaluation.concurrency
        values = (
            concurrency.turn_workers,
            concurrency.session_workers,
            concurrency.question_workers,
            concurrency.judge_workers,
        )
        if any(value <= 0 for value in values):
            raise PreflightCheckFailure("concurrency:NonPositiveLimit")
        return (
            "concurrency:"
            f"turn={values[0]}:session={values[1]}:question={values[2]}:judge={values[3]}"
        )

    def _check_credentials(self) -> str:
        completed = subprocess.run(
            (
                "git",
                "-C",
                str(self._config_root),
                "ls-files",
                "-z",
                "--",
                "src",
                "config",
                "tests",
            ),
            check=False,
            capture_output=True,
            env=_read_only_git_env(),
        )
        if completed.returncode != 0:
            raise RuntimeInvariantError("unable to enumerate tracked preflight files")
        paths = tuple(path for path in completed.stdout.split(b"\0") if path)
        matched = 0
        for raw_path in paths:
            try:
                relative = Path(os.fsdecode(raw_path))
                content = (self._config_root / relative).read_bytes()
            except OSError as error:
                raise RuntimeInvariantError("unable to scan tracked preflight files") from error
            if _SK_CREDENTIAL.search(content) is not None:
                matched += 1
        if matched:
            raise PreflightCheckFailure(f"credential_scan:CredentialPattern:files={matched}")
        return f"credential_scan:files={len(paths)}:matches=0"

    def _check_embedding(self) -> str:
        settings = self._require_settings("embedding")
        if settings.embedding.enabled:
            raise PreflightCheckFailure("embedding:Enabled")
        return "embedding:enabled=false:path_required=false"

    def _check_environment(self) -> str:
        if self._dotenv_failure is not None:
            raise PreflightCheckFailure(self._dotenv_failure)
        settings = self._require_settings("environment")
        names = tuple(
            sorted(
                {
                    settings.work.api_key_env,
                    settings.judge.api_key_env,
                    settings.es.endpoint_env,
                    settings.es.index_env,
                    settings.es.api_key_env,
                }
            )
        )
        missing = tuple(
            name for name in names if not (value := os.environ.get(name)) or not value.strip()
        )
        if missing:
            raise PreflightCheckFailure(f"environment:missing={','.join(missing)}")
        dotenv_identity = "mode=0600" if self._dotenv_path.exists() else "absent"
        return f"environment:variables={len(names)}:dotenv={dotenv_identity}"

    async def _check_model(self, name: Literal["work_model", "judge_model"]) -> str:
        settings = self._require_settings(name)
        if name == "work_model":
            model_settings = settings.work.model_copy(
                update={"max_output_tokens": settings.retrieval.answer_max_output_tokens}
            )
            api_key = settings.require_work_api_key()
        else:
            model_settings = settings.judge
            api_key = settings.require_judge_api_key()
        endpoint = _nonsecret_model_endpoint(model_settings.base_url, check_name=name)
        client = StructuredModelClient.from_model_settings(
            model_settings,
            api_key=api_key,
            supports_json_schema=True,
            trace_recorder=InMemoryTraceRecorder(),
        )
        try:
            completion = await client.complete_with_usage(
                _EvaluationProbeResponse,
                [{"role": "user", "content": 'Return exactly {"ready":true}.'}],
                TraceContext(operation="evaluation_preflight", metadata={"check": name}),
            )
            if completion.value.ready is not True:
                raise PreflightCheckFailure(f"{name}:StructuredProbeRejected")
            # The fingerprint must name the model that actually served the request, not
            # the one we asked for. A provider that silently substitutes a different
            # model would otherwise be recorded under the requested identity, which
            # makes every downstream score unattributable.
            served_model = completion.usage.model
            if served_model != model_settings.model:
                raise PreflightCheckFailure(f"{name}:ModelIdentityMismatch")
        finally:
            await client.aclose()
        return f"{name}:model={served_model}:base_url={endpoint}"

    def _check_ke_ready_snapshot(self) -> str:
        _manifest, conversations = self._load_snapshot()
        sessions = sum(len(conversation.sessions) for conversation in conversations)
        exchanges = sum(
            len(session.exchanges)
            for conversation in conversations
            for session in conversation.sessions
        )
        questions = len(normalize_questions(conversations))
        return (
            "ke_ready_snapshot:"
            f"directories=4,15,17:sessions={sessions}:exchanges={exchanges}:questions={questions}"
        )

    async def _check_ontology_identity(self) -> str:
        settings = self._require_settings("ontology_identity")
        manifest, _conversations = self._load_snapshot()
        if manifest.ontology.normalization_mode != "bounded-best-effort":
            raise PreflightCheckFailure("ontology_identity:NormalizationModeMismatch")
        ontology = ElasticsearchVocabulary.from_app_settings(settings)
        try:
            await ontology.health()
            current = await ontology.index_identity()
        finally:
            await ontology.aclose()
        if ontology.normalization_mode != "bounded-best-effort":
            raise PreflightCheckFailure("ontology_identity:NormalizationModeMismatch")
        if current != manifest.ontology.index:
            raise PreflightCheckFailure("ontology_identity:OntologyDriftError")
        return (
            "ontology_identity:"
            f"index={current.index_name}:uuid={current.index_uuid}:"
            f"mapping={current.mapping_sha256}:mode=bounded-best-effort"
        )

    def _check_state_repo(self) -> str:
        return probe_state_repository_writable(self._state_root, self._snapshot_id)

    def _load_snapshot(self) -> tuple[PipelineRunManifest, tuple[Conversation, ...]]:
        if self._snapshot_cache is not None:
            return self._snapshot_cache
        if not self._state_root.is_dir():
            raise RuntimeInvariantError("state repository is unavailable")
        artifacts = ArtifactStore(self._state_root, registry=PIPELINE_ARTIFACT_REGISTRY)
        snapshots = GitSnapshotStore(artifacts.root, artifacts)
        snapshots.verify(self._snapshot_id, self._run_id, PipelineStage.KE_READY)
        manifests = _snapshot_records_from_git(
            self._state_root,
            self._snapshot_id,
            self._run_id,
            "pipeline_manifests",
            PipelineRunManifest,
        )
        conversations = _snapshot_records_from_git(
            self._state_root,
            self._snapshot_id,
            self._run_id,
            "conversations",
            Conversation,
        )
        if len(manifests) != 1:
            raise RuntimeInvariantError(
                "verified ke-ready snapshot must contain exactly one pipeline manifest"
            )
        manifest = manifests[0]
        settings = self._require_settings("ke_ready_snapshot")
        validate_evaluation_snapshot_contract(manifest, conversations, settings)
        self._snapshot_cache = manifest, conversations
        return self._snapshot_cache

    def _require_settings(self, check_name: str) -> AppSettings:
        if self._settings is None:
            raise PreflightCheckFailure(f"{check_name}:{self._settings_error}")
        return self._settings

    def _dotenv_permission_failure(self) -> str | None:
        try:
            metadata = self._dotenv_path.lstat()
        except FileNotFoundError:
            return None
        except OSError as error:
            return f"environment:{type(error).__name__}"
        if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
            return "environment:DotenvFileTypeError"
        mode = stat.S_IMODE(metadata.st_mode)
        if mode != 0o600:
            return f"environment:dotenv_mode={mode:04o}"
        return None


def build_evaluation_preflight(
    config_root: Path | ConfigLayout,
    state_root: Path,
    run_id: str,
    snapshot_id: str,
) -> EvaluationPreflight:
    """Compose the read-only live preflight without hydrating an answer runtime."""
    return EvaluationPreflight(
        _LiveEvaluationPreflightPorts(config_root, state_root, run_id, snapshot_id)
    )


def validate_evaluation_snapshot_contract(
    manifest: PipelineRunManifest,
    conversations: Sequence[Conversation],
    settings: AppSettings,
) -> None:
    directory_ids: list[int] = []
    archive_hashes: list[str] = []
    for conversation in conversations:
        directory_id = conversation.source_metadata.get("beam_directory_id")
        archive_hash = conversation.source_metadata.get("archive_sha256")
        if isinstance(directory_id, bool) or not isinstance(directory_id, int):
            raise PreflightCheckFailure("ke_ready_snapshot:SnapshotContractMismatch")
        if not isinstance(archive_hash, str):
            raise PreflightCheckFailure("ke_ready_snapshot:SnapshotContractMismatch")
        directory_ids.append(directory_id)
        archive_hashes.append(archive_hash)
    session_count = sum(len(conversation.sessions) for conversation in conversations)
    exchange_count = sum(
        len(session.exchanges)
        for conversation in conversations
        for session in conversation.sessions
    )
    question_count = len(normalize_questions(conversations))
    actual = (
        settings.dataset.archive_sha256,
        manifest.dataset_sha256,
        tuple(sorted(set(archive_hashes))),
        settings.dataset.selected_directories,
        manifest.selected_directories,
        tuple(sorted(directory_ids)),
        settings.dataset.expected_sessions,
        session_count,
        settings.dataset.expected_exchanges,
        exchange_count,
        settings.dataset.expected_questions,
        question_count,
        settings.embedding.enabled,
        manifest.embedding_enabled,
        manifest.ontology.normalization_mode,
        manifest.concurrency,
    )
    expected = (
        _FIXED_DATASET_SHA256,
        _FIXED_DATASET_SHA256,
        (_FIXED_DATASET_SHA256,),
        _FIXED_DIRECTORIES,
        _FIXED_DIRECTORIES,
        _FIXED_DIRECTORIES,
        _FIXED_SESSIONS,
        _FIXED_SESSIONS,
        _FIXED_EXCHANGES,
        _FIXED_EXCHANGES,
        _FIXED_QUESTIONS,
        _FIXED_QUESTIONS,
        False,
        False,
        "bounded-best-effort",
        settings.evaluation.concurrency,
    )
    if actual != expected:
        raise PreflightCheckFailure("ke_ready_snapshot:SnapshotContractMismatch")
