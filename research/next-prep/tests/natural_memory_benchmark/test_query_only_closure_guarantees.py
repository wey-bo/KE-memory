"""Guarantees the query-only closure receipt must actually attest.

Phase A review findings. Each test pins one way the receipt could claim a
controlled closure that did not happen:

* an execution-level abstention still producing a `controlled_query_only_closure`
* a provider serving a different model than the one requested
* guarantee counters baked in as schema literals rather than measurements
* a result artifact written inside the memory repository
* snapshot hashes describing a different snapshot than the authority hash
* checkpoint recovery silently dropping artifacts from earlier checkpoints
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from tools.natural_memory_benchmark import e2e_openai_runtime as e2e_runtime
from tools.natural_memory_benchmark.e2e_openai_runtime import (
    MemoryWriteObserver,
    OpenAIQueryOnlyReceiptV2,
    recover_authoritative_checkpoint,
    run_openai_query_only,
)
from tools.natural_memory_benchmark.e2e_pipeline import run_e2e_pipeline
from tools.natural_memory_benchmark import query_execution_snapshot_adapter
from tools.natural_memory_benchmark.git_memory_history import (
    GitMemoryHistoryRepository,
)
from tools.natural_memory_benchmark.query_plan_v2_executor import _abstain

from test_e2e_pipeline_smoke import (  # noqa: F401
    _chat_response,
    _L1Producer,
    _L2Producer,
    _production_query_payload,
    _QueryProducer,
    _SequencedOpener,
    _turns,
)


def _seeded_repository(tmp_path: Path, name: str = "guarantee-history.git"):
    repository = tmp_path / name
    initial = run_e2e_pipeline(
        turns=_turns(),
        l1_producer=_L1Producer(),
        l2_producer=_L2Producer(),
        query_producer=_QueryProducer(),
        repository_path=repository,
        question="What beverage is preferred?",
    )
    return repository, initial


def _query_only(
    repository: Path,
    initial: Any,
    result_path: Path,
    *,
    opener: Any,
    model: str = "test-model",
) -> Any:
    return run_openai_query_only(
        question="What beverage is preferred?",
        query_time="2026-07-31T00:00:00Z",
        repository_path=repository,
        expected_git_commit=initial.snapshot.git_commit,
        expected_checkpoint_id=initial.snapshot.checkpoint_id,
        result_path=result_path,
        base_url="https://model.invalid/v1",
        api_key="credential-that-must-not-enter-artifacts",
        model=model,
        timeout_seconds=37,
        max_attempts=1,
        opener=opener,
    )


def test_an_observed_extraction_call_aborts_the_attempt(tmp_path: Path) -> None:
    """The zero count must come from the observer, not from a constant.

    Asserting the count equals zero is satisfied by a hardcoded zero too, so
    this forces a real extraction construction inside the window and requires
    the guard to notice it. If the receipt field were wired to a constant, the
    attempt would succeed instead of being refused.
    """
    repository, initial = _seeded_repository(tmp_path, "counted-history.git")
    result_path = tmp_path / "counted-result.json"
    real_execute = e2e_runtime.execute_authoritative_query

    def executing_after_building_a_producer(**kwargs: Any) -> Any:
        try:
            e2e_runtime.OpenAICompatibleL1BatchProducer(  # type: ignore[call-arg]
                registry=None,
                policy=None,
                base_url="https://model.invalid/v1",
                api_key="k",
                model="m",
            )
        except Exception:
            pass
        return real_execute(**kwargs)

    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            e2e_runtime,
            "execute_authoritative_query",
            executing_after_building_a_producer,
        )
        with pytest.raises(ValueError, match="no extraction calls"):
            _query_only(
                repository,
                initial,
                result_path,
                opener=opener,
                model="test-model-response",
            )
    assert not result_path.exists()


def test_extraction_counts_come_from_an_observer(tmp_path: Path) -> None:
    """The zero extraction count must be observed, not written in by hand."""
    repository, initial = _seeded_repository(tmp_path, "extraction-history.git")
    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    seen: list[str] = []
    real_observer = e2e_runtime.ExtractionCallObserver

    class _RecordingObserver(real_observer):  # type: ignore[misc,valid-type]
        def __exit__(self, *args: object) -> None:
            seen.append("closed")
            super().__exit__(*args)

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(e2e_runtime, "ExtractionCallObserver", _RecordingObserver)
        outcome = _query_only(
            repository,
            initial,
            tmp_path / "extraction-result.json",
            opener=opener,
            model="test-model-response",
        )
    assert seen == ["closed"], "the attempt must run inside an extraction observer"
    assert outcome.receipt.l1_producer_call_count == 0
    assert outcome.receipt.l2_producer_call_count == 0


def test_constructing_an_extraction_producer_is_counted() -> None:
    """A producer built during the window must raise the recorded count."""
    real_l1 = e2e_runtime.OpenAICompatibleL1BatchProducer
    real_l2 = e2e_runtime.OpenAICompatibleL2Producer
    with e2e_runtime.ExtractionCallObserver() as observer:
        assert observer.l1_count == 0 and observer.l2_count == 0
        assert e2e_runtime.OpenAICompatibleL1BatchProducer is not real_l1, (
            "the producer name must actually be patched inside the window"
        )
        try:
            e2e_runtime.OpenAICompatibleL1BatchProducer(  # type: ignore[call-arg]
                registry=None,
                policy=None,
                base_url="https://model.invalid/v1",
                api_key="k",
                model="m",
            )
        except Exception:
            pass
        assert observer.l1_count == 1, (
            "constructing an L1 producer must be observed even if it then fails"
        )
    # Compare against the real classes, not the wrapper factory: the factory is
    # never the installed value, so asserting against it proves nothing.
    assert e2e_runtime.OpenAICompatibleL1BatchProducer is real_l1
    assert e2e_runtime.OpenAICompatibleL2Producer is real_l2


def test_extraction_observation_windows_cannot_nest() -> None:
    """A second observer must be refused, not left leaking a wrapper."""
    real_l1 = e2e_runtime.OpenAICompatibleL1BatchProducer
    outer = e2e_runtime.ExtractionCallObserver()
    inner = e2e_runtime.ExtractionCallObserver()
    with outer:
        with pytest.raises(RuntimeError, match="must not nest"):
            inner.__enter__()
    assert e2e_runtime.OpenAICompatibleL1BatchProducer is real_l1
    assert e2e_runtime.ExtractionCallObserver._active is None


def test_write_observation_windows_cannot_nest() -> None:
    """The same guard must hold for the write observer."""
    before = {
        name: GitMemoryHistoryRepository.__dict__.get(name)
        for name in MemoryWriteObserver.WRITE_METHODS
    }
    outer = MemoryWriteObserver()
    inner = MemoryWriteObserver()
    with outer.observing("recovery"):
        with pytest.raises(RuntimeError, match="must not nest"):
            inner.observing("snapshot").__enter__()
    for name, descriptor in before.items():
        assert GitMemoryHistoryRepository.__dict__.get(name) is descriptor
    assert MemoryWriteObserver._active is None


def test_inactive_extraction_observer_is_refused(tmp_path: Path) -> None:
    """An unobserved attempt must not be able to emit a receipt."""
    repository, initial = _seeded_repository(tmp_path, "inactive-history.git")
    result_path = tmp_path / "inactive-result.json"
    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    with pytest.raises(ValueError, match="active extraction observer"):
        e2e_runtime._run_openai_query_only(
            question="What beverage is preferred?",
            query_time="2026-07-31T00:00:00Z",
            repository_path=repository,
            expected_git_commit=initial.snapshot.git_commit,
            expected_checkpoint_id=initial.snapshot.checkpoint_id,
            result_path=result_path,
            query_id="query-e2e-1",
            base_url="https://model.invalid/v1",
            api_key="k",
            model="test-model-response",
            timeout_seconds=37,
            max_attempts=1,
            opener=opener,
            extraction_observer=e2e_runtime.ExtractionCallObserver(),
        )
    assert not result_path.exists()


def _sample_receipt_payload(tmp_path: Path | None = None) -> dict[str, Any]:
    """A real receipt payload, so the loader is tested against genuine shapes."""
    root = tmp_path or Path(tempfile.mkdtemp())
    repository, initial = _seeded_repository(root, "loader-history.git")
    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    outcome = _query_only(
        repository,
        initial,
        root / "loader-result.json",
        opener=opener,
        model="test-model-response",
    )
    return outcome.receipt.model_dump(mode="json")


def test_every_frozen_receipt_shape_is_loadable() -> None:
    """Frozen receipts must stay machine-readable without editing the bytes.

    Three shapes exist: the original asserted-counter v1, the transitional
    payloads written while v1 was being changed in place (v1 label, measured
    shape), and v2. A reader must be able to load all three, so this validates
    real payloads rather than inspecting field declarations.
    """
    measured = _sample_receipt_payload()
    asserted_v1 = {
        key: value
        for key, value in measured.items()
        if key != "observed_write_phases"
    }
    asserted_v1["schema_version"] = "openai-query-only-receipt-v1"
    transitional = {
        **asserted_v1,
        "observed_write_phases": list(measured["observed_write_phases"]),
    }
    measured_v2 = {
        **transitional,
        "schema_version": "openai-query-only-receipt-v2",
    }
    for label, payload, expected in (
        ("asserted v1", asserted_v1, e2e_runtime.OpenAIQueryOnlyReceiptV1),
        (
            "transitional v1",
            transitional,
            e2e_runtime.OpenAIQueryOnlyReceiptV1Transitional,
        ),
        ("measured v2", measured_v2, OpenAIQueryOnlyReceiptV2),
    ):
        loaded = e2e_runtime.load_query_only_receipt(payload)
        assert isinstance(loaded, expected), label
        assert loaded.model_dump(mode="json") == payload, (
            f"{label} must round-trip unchanged"
        )
    with pytest.raises(ValueError, match="unknown query-only receipt schema"):
        e2e_runtime.load_query_only_receipt({"schema_version": "nope"})


def test_receipt_counters_are_measured_not_schema_constants() -> None:
    """A receipt whose counters cannot express a violation proves nothing."""
    fields = OpenAIQueryOnlyReceiptV2.model_fields
    for name in (
        "query_call_count",
        "l1_producer_call_count",
        "l2_producer_call_count",
        "automatic_memory_write_count",
    ):
        annotation = repr(fields[name].annotation)
        assert "Literal" not in annotation, (
            f"{name} is pinned as {annotation}; it must carry a measured value "
            "so that a violated guarantee is representable and detectable"
        )
        assert fields[name].is_required(), (
            f"{name} must be supplied from a measurement at construction"
        )


def test_write_observer_restores_descriptors_exactly() -> None:
    """Observing writes must not corrupt the repository class afterwards."""
    before = {
        name: GitMemoryHistoryRepository.__dict__.get(name)
        for name in MemoryWriteObserver.WRITE_METHODS
    }
    with MemoryWriteObserver():
        pass
    for name, descriptor in before.items():
        assert GitMemoryHistoryRepository.__dict__.get(name) is descriptor, (
            f"{name} was not restored to its original descriptor"
        )
    try:
        with MemoryWriteObserver():
            raise RuntimeError("observed failure")
    except RuntimeError:
        pass
    for name, descriptor in before.items():
        assert GitMemoryHistoryRepository.__dict__.get(name) is descriptor, (
            f"{name} leaked a patched descriptor after an exception"
        )


def test_a_stray_write_during_the_attempt_aborts_it(tmp_path: Path) -> None:
    """A write smuggled into the attempt must be counted and refuse the receipt."""
    repository, initial = _seeded_repository(tmp_path, "stray-write-history.git")
    result_path = tmp_path / "stray-write-result.json"
    real_execute = e2e_runtime.execute_authoritative_query

    def executing_with_a_stray_write(**kwargs: Any) -> Any:
        GitMemoryHistoryRepository(kwargs["repository_path"])._git(
            "update-ref",
            "refs/heads/stray-probe",
            initial.snapshot.git_commit,
        )
        return real_execute(**kwargs)

    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            e2e_runtime,
            "execute_authoritative_query",
            executing_with_a_stray_write,
        )
        with pytest.raises(ValueError, match="no extraction calls, and no writes"):
            _query_only(
                repository,
                initial,
                result_path,
                opener=opener,
                model="test-model-response",
            )
    assert not result_path.exists()


def test_write_observer_counts_direct_git_mutation(tmp_path: Path) -> None:
    """The generic git primitive must not be an unobserved write bypass."""
    repository, initial = _seeded_repository(tmp_path, "bypass-history.git")
    history = GitMemoryHistoryRepository(repository)
    head = history.head_commit()
    with MemoryWriteObserver() as observer:
        # A read-only plumbing call must not be counted.
        history._git("rev-parse", "refs/heads/authoritative")
        assert observer.count == 0
        # A ref mutation reached directly through the primitive must be.
        history._git(
            "update-ref",
            "refs/heads/observed-probe",
            head,
        )
        assert observer.count == 1, (
            "a direct update-ref through the git primitive must be observed"
        )
    assert initial.snapshot.git_commit == head


def test_unlisted_git_verbs_count_as_writes() -> None:
    """The verb filter must fail closed, so an unknown verb is a write."""
    observer = MemoryWriteObserver()
    # read-tree mutates the index and is used by the commit builder, so a
    # mutating-verb allowlist that omitted it would have been fail-open.
    assert observer._mutates((None, "read-tree", "--empty")) is True
    assert observer._mutates((None, "some-future-plumbing-verb")) is True
    assert observer._mutates((None,)) is True
    for verb in ("cat-file", "ls-tree", "rev-list", "rev-parse", "show"):
        assert observer._mutates((None, verb)) is False, verb
    # A read-only verb appearing as an argument must not mask a mutating verb.
    assert observer._mutates((None, "update-ref", "refs/heads/show")) is True


def test_write_observer_covers_the_repository_write_surface() -> None:
    """The observed method list must not silently miss a write entry point."""
    observed = set(MemoryWriteObserver.WRITE_METHODS)
    missing = [
        name
        for name in ("initialize", "commit_checkpoint", "prepare_hard_purge")
        if name not in observed
    ]
    assert missing == [], f"unobserved write entry points: {missing}"


def test_query_only_counts_writes_across_the_whole_attempt(
    tmp_path: Path,
) -> None:
    """A write anywhere in the attempt must be counted, not just during execution."""
    repository, initial = _seeded_repository(tmp_path, "window-history.git")
    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    outcome = _query_only(
        repository,
        initial,
        tmp_path / "window-result.json",
        opener=opener,
        model="test-model-response",
    )
    assert outcome.receipt.automatic_memory_write_count == 0
    # The recorded value must come from an observation that spans recovery,
    # snapshot verification and execution, so a write in any of those phases
    # would be visible rather than hidden outside the observed window.
    assert outcome.receipt.observed_write_phases == (
        "recovery",
        "snapshot",
        "compilation",
        "execution",
    )


def test_query_only_rejects_response_model_mismatch(tmp_path: Path) -> None:
    """A downgraded or substituted model must fail the attempt, not pass it."""
    repository, initial = _seeded_repository(tmp_path)
    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    with pytest.raises(ValueError, match="response model"):
        _query_only(
            repository,
            initial,
            tmp_path / "mismatch-result.json",
            opener=opener,
            model="test-model",
        )
    assert not (tmp_path / "mismatch-result.json").exists()


def test_execution_level_abstention_is_gated(tmp_path: Path) -> None:
    """The executor declining must abort the attempt, not yield a receipt.

    The sibling test below is blocked earlier, by the compilation gate, so this
    one drives a genuinely abstained execution to reach the execution gate.
    """
    repository, initial = _seeded_repository(tmp_path, "exec-abstain-history.git")
    result_path = tmp_path / "exec-abstain-result.json"

    def abstaining_evaluation(plan: Any, snapshot: Any) -> Any:
        return _abstain(plan, "no_matching_facts")

    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            query_execution_snapshot_adapter,
            "_evaluate_compiled_query_snapshot",
            abstaining_evaluation,
        )
        with pytest.raises(ValueError, match="abstained instead of closing"):
            _query_only(
                repository,
                initial,
                result_path,
                opener=opener,
                model="test-model-response",
            )
    assert not result_path.exists()


def test_unsupported_absence_request_is_gated_at_compilation(
    tmp_path: Path,
) -> None:
    """An unanswerable absence request must not yield a closure receipt.

    This input is refused by the compilation gate rather than the execution
    gate; the execution gate is covered by the test above.
    """
    repository, initial = _seeded_repository(tmp_path)
    payload = _production_query_payload()
    # Require an explicit absence the snapshot cannot establish, so the
    # deterministic executor abstains instead of returning evidence.
    payload["explicit_absence_requested"] = True
    payload["evidence_policy"] = "require_explicit_absence"
    opener = _SequencedOpener([_chat_response(payload, include_model=True)])
    result_path = tmp_path / "abstained-result.json"
    with pytest.raises(ValueError):
        _query_only(
            repository,
            initial,
            result_path,
            opener=opener,
            model="test-model-response",
        )
    assert not result_path.exists()


def test_query_only_refuses_result_path_inside_repository(tmp_path: Path) -> None:
    """The query-only path must not create files inside the memory repository."""
    repository, initial = _seeded_repository(tmp_path)
    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    inside = repository / "objects" / "info" / "alternates"
    with pytest.raises(ValueError, match="repository"):
        _query_only(
            repository,
            initial,
            inside,
            opener=opener,
            model="test-model-response",
        )
    assert not inside.exists()


def test_receipt_snapshot_hashes_match_the_executed_authority(
    tmp_path: Path,
) -> None:
    """Receipt snapshot hashes must describe the snapshot that was executed."""
    repository, initial = _seeded_repository(tmp_path)
    opener = _SequencedOpener([_chat_response(_production_query_payload())])
    outcome = _query_only(
        repository,
        initial,
        tmp_path / "hash-result.json",
        opener=opener,
        model="test-model-response",
    )
    authority = outcome.pipeline.execution.authority
    assert outcome.receipt.snapshot.snapshot_sha256 == authority.snapshot_sha256
    assert outcome.receipt.snapshot.registry_sha256 == authority.registry_sha256
    assert outcome.receipt.snapshot.authority_sha256 == authority.authority_sha256


def test_recovery_states_its_single_checkpoint_precondition(
    tmp_path: Path,
) -> None:
    """Recovery must not silently drop artifacts published by earlier checkpoints."""
    repository, initial = _seeded_repository(tmp_path, "multi-history.git")
    recovered = recover_authoritative_checkpoint(
        repository_path=repository,
        expected_git_commit=initial.snapshot.git_commit,
        expected_checkpoint_id=initial.snapshot.checkpoint_id,
    )
    manifest = recovered.repository.read_checkpoint_manifest(
        commit=recovered.git_commit
    )
    turn_bundle_paths = {
        descriptor.path
        for descriptor in manifest.artifacts
        if descriptor.artifact_kind == "turn_bundle"
    }
    all_record_paths = {
        path
        for path in recovered.repository._git(
            "ls-tree", "-r", "--name-only", recovered.git_commit, "--", "records"
        ).splitlines()
        if "/turn_bundle/" in path
    }
    assert turn_bundle_paths == all_record_paths, (
        "recovery reads turn bundles from the head manifest only; when the "
        "history has more than one checkpoint that set is incomplete, so the "
        "precondition must be enforced explicitly rather than left latent"
    )
    assert len(recovered.turn_bundles) == len(all_record_paths)
