from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from .ledger import validate_external_results_ledger
from .evidence import export_evidence_corpus_file, export_gold_evidence_file
from .dense_runner import run_dense_reference_file
from .scoring import score_results_file
from .authoritative_conformance_runner import run_authoritative_conformance_file
from .identity_conformance_runner import run_identity_conformance_file
from .identity_candidate_assessment import run_identity_candidate_assessment_file
from .extraction_bridge_assessment import run_extraction_bridge_assessment
from .typed_extractor_l1 import (
    prepare_l1_dev_slice,
    run_l1_scoring_file,
    validate_l1_dev_slice,
)
from .typed_extractor_l1_dev_repair import (
    prepare_l1_dev_repair_slice,
    validate_l1_dev_repair_slice,
)
from .typed_extractor_model_run import (
    freeze_l1_model_proposals,
    write_l1_model_dispatch,
)
from .typed_extractor_l2 import (
    prepare_l2_dev_slice,
    run_l2_scoring_file,
    validate_l2_dev_slice,
)
from .typed_extractor_l2_dev_repair import (
    prepare_l2_dev_repair_slice,
    validate_l2_dev_repair_slice,
)
from .typed_extractor_dev_repair_qualification import qualify_dev_repair
from .typed_extractor_l2_model_run import (
    freeze_l2_model_proposals,
    write_l2_model_dispatch,
)
from .typed_extractor_fresh_prereg import (
    freeze_typed_extractor_fresh_preregistration,
    validate_typed_extractor_fresh_preregistration,
)
from .typed_extractor_fresh_v2_prereg import (
    freeze_typed_extractor_fresh_v2_preregistration,
    validate_typed_extractor_fresh_v2_preregistration,
)
from .typed_extractor_fresh_v3_prereg import (
    freeze_typed_extractor_fresh_v3_preregistration,
    validate_typed_extractor_fresh_v3_preregistration,
)
from .identity_proposal import (
    freeze_natural_identity_slice,
    validate_natural_identity_slice,
)
from .identity_proposal_runner import (
    run_reference_identity_proposer_file,
    score_identity_proposals_file,
)
from .identity_model_run import (
    freeze_identity_model_proposals,
    write_identity_model_dispatch,
)
from .identity_proposal_opaque import (
    prepare_opaque_identity_slice,
    validate_opaque_identity_slice,
)
from .identity_proposal_fresh import (
    prepare_fresh_identity_slice,
    validate_fresh_identity_slice,
)
from .identity_proposer_policy import (
    DEV_CASE_COUNT,
    DEV_DATASET_ID,
    FINAL_CASE_COUNT,
    freeze_identity_proposer_policy,
    prepare_identity_dev_slice,
)
from .representation_conformance_runner import run_representation_conformance_file
from .semantic_ir_keol_projection import project_semantic_ir_slice_suite_to_keol_file
from .semantic_ir_keol_trace import write_projection_trace_report
from .semantic_ir_keol_validate import validate_keol_projection_file
from .semantic_ir_runner import run_semantic_ir_diagnostics_file
from .semantic_ir_slice_runner import run_real_slice_semantic_ir_diagnostics_file
from .slices import freeze_slice_bundle, validate_slice_bundle
from .symbolic_fallback_runner import run_symbolic_fallback_file
from .symbolic_runner import run_symbolic_file


DEFAULT_ROOT = Path("artifacts") / "natural-benchmark-slices"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="natural-memory-benchmark")
    commands = parser.add_subparsers(dest="command", required=True)

    freeze = commands.add_parser("freeze-slice")
    freeze.add_argument("--raw-root", default=str(DEFAULT_ROOT))
    freeze.add_argument("--root", required=True)
    freeze.add_argument("--slice-id", default="slice-v1")

    validate_slice = commands.add_parser("validate-slice")
    validate_slice.add_argument("--root", required=True)
    validate_slice.add_argument("--slice-id", default="slice-v1")

    validate_ledger = commands.add_parser("validate-ledger")
    validate_ledger.add_argument("--path", required=True)

    score_results = commands.add_parser("score-results")
    score_results.add_argument("--root", required=True)
    score_results.add_argument("--slice-id", default="slice-v1")
    score_results.add_argument("--results", required=True)
    score_results.add_argument("--output", required=True)

    export_evidence = commands.add_parser("export-gold-evidence")
    export_evidence.add_argument("--root", required=True)
    export_evidence.add_argument("--slice-id", default="slice-v1")
    export_evidence.add_argument("--output", required=True)

    export_corpus = commands.add_parser("export-evidence-corpus")
    export_corpus.add_argument("--root", required=True)
    export_corpus.add_argument("--slice-id", default="slice-v1")
    export_corpus.add_argument("--output", required=True)

    dense = commands.add_parser("run-dense-reference")
    dense.add_argument("--slice", required=True)
    dense.add_argument("--corpus", required=True)
    dense.add_argument("--output", required=True)
    dense.add_argument("--run-id", required=True)
    dense.add_argument("--top-k", type=int, default=10)
    dense.add_argument("--encoder", choices=["lexical", "fastembed"], default="fastembed")

    symbolic = commands.add_parser("run-symbolic")
    symbolic.add_argument("--slice", required=True)
    symbolic.add_argument("--corpus", required=True)
    symbolic.add_argument("--output", required=True)
    symbolic.add_argument("--run-id", required=True)
    symbolic.add_argument("--top-k", type=int, default=10)

    symbolic_fallback = commands.add_parser("run-symbolic-fallback")
    symbolic_fallback.add_argument("--slice", required=True)
    symbolic_fallback.add_argument("--corpus", required=True)
    symbolic_fallback.add_argument("--output", required=True)
    symbolic_fallback.add_argument("--run-id", required=True)
    symbolic_fallback.add_argument("--symbolic-top-k", type=int, default=10)
    symbolic_fallback.add_argument("--fallback-top-k", type=int, default=10)
    symbolic_fallback.add_argument("--encoder", choices=["lexical", "fastembed"], default="fastembed")

    semantic_ir = commands.add_parser("run-semantic-ir-diagnostics")
    semantic_ir.add_argument("--output", required=True)
    semantic_ir.add_argument("--report", required=True)
    semantic_ir.add_argument("--run-id", required=True)

    semantic_ir_slice = commands.add_parser("run-semantic-ir-slice-diagnostics")
    semantic_ir_slice.add_argument("--root", required=True)
    semantic_ir_slice.add_argument("--slice-id", default="slice-v1")
    semantic_ir_slice.add_argument("--results", required=True)
    semantic_ir_slice.add_argument("--output", required=True)
    semantic_ir_slice.add_argument("--report", required=True)
    semantic_ir_slice.add_argument("--run-id", required=True)

    semantic_ir_keol = commands.add_parser("project-semantic-ir-slice-to-keol")
    semantic_ir_keol.add_argument("--root", required=True)
    semantic_ir_keol.add_argument("--slice-id", default="slice-v1")
    semantic_ir_keol.add_argument("--results", required=True)
    semantic_ir_keol.add_argument("--output", required=True)
    semantic_ir_keol.add_argument("--workflow-run-id", required=True)

    semantic_ir_trace = commands.add_parser("trace-semantic-ir-keol-projection")
    semantic_ir_trace.add_argument("--projection", required=True)
    semantic_ir_trace.add_argument("--output", required=True)
    semantic_ir_trace.add_argument("--report", required=True)

    representation_conformance = commands.add_parser("run-representation-conformance")
    representation_conformance.add_argument("--root", required=True)
    representation_conformance.add_argument("--slice-id", default="slice-v1")
    representation_conformance.add_argument("--results", required=True)
    representation_conformance.add_argument("--output", required=True)
    representation_conformance.add_argument("--report", required=True)
    representation_conformance.add_argument("--run-id", required=True)

    authoritative_conformance = commands.add_parser("run-authoritative-conformance")
    authoritative_conformance.add_argument("--root", required=True)
    authoritative_conformance.add_argument("--slice-id", default="slice-v1")
    authoritative_conformance.add_argument("--results", required=True)
    authoritative_conformance.add_argument("--output", required=True)
    authoritative_conformance.add_argument("--report", required=True)
    authoritative_conformance.add_argument("--run-id", required=True)
    authoritative_conformance.add_argument("--workspace-root")

    identity_conformance = commands.add_parser("run-identity-conformance")
    identity_conformance.add_argument("--root", required=True)
    identity_conformance.add_argument("--output", required=True)
    identity_conformance.add_argument("--report", required=True)
    identity_conformance.add_argument("--run-id", required=True)
    identity_conformance.add_argument("--workspace-root")

    freeze_identity = commands.add_parser("freeze-natural-identity-slice")
    freeze_identity.add_argument("--source-config", required=True)
    freeze_identity.add_argument("--output-root", required=True)
    freeze_identity.add_argument("--workspace-root")

    validate_identity = commands.add_parser("validate-natural-identity-slice")
    validate_identity.add_argument("--root", required=True)
    validate_identity.add_argument("--workspace-root")

    prepare_opaque_identity = commands.add_parser(
        "prepare-natural-identity-opaque-slice"
    )
    prepare_opaque_identity.add_argument("--v1-source", required=True)
    prepare_opaque_identity.add_argument("--output-root", required=True)
    prepare_opaque_identity.add_argument("--workspace-root")

    validate_opaque_identity = commands.add_parser(
        "validate-natural-identity-opaque-slice"
    )
    validate_opaque_identity.add_argument("--v1-source", required=True)
    validate_opaque_identity.add_argument("--root", required=True)
    validate_opaque_identity.add_argument("--workspace-root")

    prepare_fresh_identity = commands.add_parser(
        "prepare-natural-identity-fresh-slice"
    )
    prepare_fresh_identity.add_argument("--v2-source", required=True)
    prepare_fresh_identity.add_argument("--hidden-source", required=True)
    prepare_fresh_identity.add_argument("--output-root", required=True)
    prepare_fresh_identity.add_argument("--policy-freeze", required=True)
    prepare_fresh_identity.add_argument("--workspace-root")

    validate_fresh_identity = commands.add_parser(
        "validate-natural-identity-fresh-slice"
    )
    validate_fresh_identity.add_argument("--v2-source", required=True)
    validate_fresh_identity.add_argument("--hidden-source", required=True)
    validate_fresh_identity.add_argument("--root", required=True)
    validate_fresh_identity.add_argument("--policy-freeze", required=True)
    validate_fresh_identity.add_argument("--workspace-root")

    prepare_identity_dev = commands.add_parser("prepare-identity-dev-slice")
    prepare_identity_dev.add_argument("--v2-source", required=True)
    prepare_identity_dev.add_argument("--output-root", required=True)
    prepare_identity_dev.add_argument("--workspace-root")

    freeze_proposer_policy = commands.add_parser(
        "freeze-identity-proposer-policy"
    )
    freeze_proposer_policy.add_argument("--policy", required=True)
    freeze_proposer_policy.add_argument("--dev-prompt", required=True)
    freeze_proposer_policy.add_argument("--final-prompt", required=True)
    freeze_proposer_policy.add_argument("--output", required=True)
    freeze_proposer_policy.add_argument("--dev-public", required=True)
    freeze_proposer_policy.add_argument("--final-public", required=True)
    freeze_proposer_policy.add_argument("--dev-run-id", required=True)
    freeze_proposer_policy.add_argument("--final-run-id", required=True)
    freeze_proposer_policy.add_argument("--proposer-id", required=True)
    freeze_proposer_policy.add_argument("--proposer-version", required=True)
    freeze_proposer_policy.add_argument(
        "--dev-dataset-id", default=DEV_DATASET_ID
    )
    freeze_proposer_policy.add_argument(
        "--dev-case-count", type=int, default=DEV_CASE_COUNT
    )
    freeze_proposer_policy.add_argument(
        "--final-case-count", type=int, default=FINAL_CASE_COUNT
    )

    prepare_model_dispatch = commands.add_parser("prepare-identity-model-dispatch")
    prepare_model_dispatch.add_argument("--public", required=True)
    prepare_model_dispatch.add_argument("--prompt", required=True)
    prepare_model_dispatch.add_argument("--output", required=True)
    prepare_model_dispatch.add_argument("--run-id", required=True)
    prepare_model_dispatch.add_argument("--proposer-id", required=True)
    prepare_model_dispatch.add_argument("--proposer-version", required=True)
    prepare_model_dispatch.add_argument(
        "--isolation-context",
        required=True,
        choices=["fresh-agent-no-history-declarative"],
    )

    freeze_model_proposals = commands.add_parser("freeze-identity-model-proposals")
    freeze_model_proposals.add_argument("--public", required=True)
    freeze_model_proposals.add_argument("--staged-proposals", required=True)
    freeze_model_proposals.add_argument("--output", required=True)
    freeze_model_proposals.add_argument("--provenance", required=True)
    freeze_model_proposals.add_argument("--prompt", required=True)
    freeze_model_proposals.add_argument("--dispatch", required=True)
    freeze_model_proposals.add_argument(
        "--isolation-context",
        required=True,
        choices=["fresh-agent-no-history-declarative"],
    )

    propose_identity = commands.add_parser("run-identity-proposal-reference")
    propose_identity.add_argument("--public", required=True)
    propose_identity.add_argument("--output", required=True)
    propose_identity.add_argument("--run-id", required=True)

    score_identity = commands.add_parser("score-identity-proposals")
    score_identity.add_argument("--root", required=True)
    score_identity.add_argument("--proposals", required=True)
    score_identity.add_argument("--output", required=True)
    score_identity.add_argument("--report", required=True)
    score_identity.add_argument("--workspace-root")

    assess_identity_candidates = commands.add_parser(
        "assess-identity-candidate-generation"
    )
    assess_identity_candidates.add_argument("--public", required=True)
    assess_identity_candidates.add_argument("--proposals", required=True)
    assess_identity_candidates.add_argument("--score", required=True)
    assess_identity_candidates.add_argument("--experiment-root", required=True)
    assess_identity_candidates.add_argument("--guard-scenario-id", required=True)
    assess_identity_candidates.add_argument("--queue", required=True)
    assess_identity_candidates.add_argument("--output", required=True)
    assess_identity_candidates.add_argument("--report", required=True)

    assess_extraction = commands.add_parser(
        "assess-automatic-l1-l2-extraction"
    )
    assess_extraction.add_argument("--source", required=True)
    assess_extraction.add_argument("--turn-manifest", required=True)
    assess_extraction.add_argument("--dialogue-manifest", required=True)
    assess_extraction.add_argument("--final-knowledge", required=True)
    assess_extraction.add_argument("--run", required=True)
    assess_extraction.add_argument("--source-segments", required=True)
    assess_extraction.add_argument("--guard-root", required=True)
    assess_extraction.add_argument("--guard-slice-id", default="slice-v1")
    assess_extraction.add_argument("--guard-results", required=True)
    assess_extraction.add_argument("--ledger", required=True)
    assess_extraction.add_argument("--output", required=True)
    assess_extraction.add_argument("--report", required=True)

    prepare_typed_l1 = commands.add_parser("prepare-typed-extractor-l1-dev")
    validate_typed_l1 = commands.add_parser("validate-typed-extractor-l1-dev")
    for typed_l1 in (prepare_typed_l1, validate_typed_l1):
        typed_l1.add_argument("--source-config", required=True)
        typed_l1.add_argument("--prompt", required=True)
        typed_l1.add_argument("--bridge-ledger", required=True)
        typed_l1.add_argument("--source", required=True)
        typed_l1.add_argument("--turn-manifest", required=True)
        typed_l1.add_argument("--dialogue-manifest", required=True)
        typed_l1.add_argument("--final-knowledge", required=True)
        typed_l1.add_argument("--run", required=True)
        typed_l1.add_argument("--source-segments", required=True)
    prepare_typed_l1.add_argument("--output-root", required=True)
    validate_typed_l1.add_argument("--root", required=True)

    prepare_typed_l1_repair = commands.add_parser(
        "prepare-typed-extractor-l1-dev-repair"
    )
    validate_typed_l1_repair = commands.add_parser(
        "validate-typed-extractor-l1-dev-repair"
    )
    for typed_l1_repair in (prepare_typed_l1_repair, validate_typed_l1_repair):
        typed_l1_repair.add_argument("--source", required=True)
        typed_l1_repair.add_argument(
            "--prior-root", action="append", required=True
        )
    prepare_typed_l1_repair.add_argument("--output-root", required=True)
    validate_typed_l1_repair.add_argument("--root", required=True)

    typed_l1_dispatch = commands.add_parser(
        "prepare-typed-extractor-l1-dispatch"
    )
    typed_l1_dispatch.add_argument("--public", required=True)
    typed_l1_dispatch.add_argument("--prompt", required=True)
    typed_l1_dispatch.add_argument("--output", required=True)
    typed_l1_dispatch.add_argument("--run-id", required=True)
    typed_l1_dispatch.add_argument("--proposer-id", required=True)
    typed_l1_dispatch.add_argument("--proposer-version", required=True)
    typed_l1_dispatch.add_argument("--requested-model", required=True)
    typed_l1_dispatch.add_argument(
        "--isolation-context",
        required=True,
        choices=["fresh-agent-no-history-declarative"],
    )

    typed_l1_freeze = commands.add_parser(
        "freeze-typed-extractor-l1-proposals"
    )
    typed_l1_freeze.add_argument("--public", required=True)
    typed_l1_freeze.add_argument("--staged-proposals", required=True)
    typed_l1_freeze.add_argument("--output", required=True)
    typed_l1_freeze.add_argument("--provenance", required=True)
    typed_l1_freeze.add_argument("--prompt", required=True)
    typed_l1_freeze.add_argument("--dispatch", required=True)
    typed_l1_freeze.add_argument("--raw-response", required=True)
    typed_l1_freeze.add_argument(
        "--isolation-context",
        required=True,
        choices=["fresh-agent-no-history-declarative"],
    )

    typed_l1_score = commands.add_parser(
        "score-typed-extractor-l1-proposals"
    )
    typed_l1_score.add_argument("--root", required=True)
    typed_l1_score.add_argument("--proposals", required=True)
    typed_l1_score.add_argument("--provenance", required=True)
    typed_l1_score.add_argument("--guard-root", required=True)
    typed_l1_score.add_argument("--guard-slice-id", default="slice-v1")
    typed_l1_score.add_argument("--guard-results", required=True)
    typed_l1_score.add_argument("--output", required=True)
    typed_l1_score.add_argument("--report", required=True)
    typed_l1_score.add_argument("--error-analysis", required=True)

    prepare_typed_l2 = commands.add_parser("prepare-typed-extractor-l2-dev")
    validate_typed_l2 = commands.add_parser("validate-typed-extractor-l2-dev")
    for typed_l2 in (prepare_typed_l2, validate_typed_l2):
        typed_l2.add_argument("--source-config", required=True)
        typed_l2.add_argument("--prompt", required=True)
        typed_l2.add_argument("--bridge-ledger", required=True)
        typed_l2.add_argument("--source", required=True)
        typed_l2.add_argument("--turn-manifest", required=True)
        typed_l2.add_argument("--dialogue-manifest", required=True)
        typed_l2.add_argument("--final-knowledge", required=True)
        typed_l2.add_argument("--run", required=True)
        typed_l2.add_argument("--source-segments", required=True)
        typed_l2.add_argument("--l1-qualification-root", required=True)
    prepare_typed_l2.add_argument("--output-root", required=True)
    validate_typed_l2.add_argument("--root", required=True)

    prepare_typed_l2_repair = commands.add_parser(
        "prepare-typed-extractor-l2-dev-repair"
    )
    validate_typed_l2_repair = commands.add_parser(
        "validate-typed-extractor-l2-dev-repair"
    )
    for typed_l2_repair in (prepare_typed_l2_repair, validate_typed_l2_repair):
        typed_l2_repair.add_argument("--source", required=True)
        typed_l2_repair.add_argument(
            "--prior-root", action="append", required=True
        )
    prepare_typed_l2_repair.add_argument("--output-root", required=True)
    validate_typed_l2_repair.add_argument("--root", required=True)

    qualify_typed_repair = commands.add_parser(
        "qualify-typed-extractor-dev-repair"
    )
    qualify_typed_repair.add_argument("--layer", choices=["l1", "l2"], required=True)
    qualify_typed_repair.add_argument("--score", required=True)
    qualify_typed_repair.add_argument("--output", required=True)
    qualify_typed_repair.add_argument("--report", required=True)

    typed_l2_dispatch = commands.add_parser(
        "prepare-typed-extractor-l2-dispatch"
    )
    typed_l2_dispatch.add_argument("--public", required=True)
    typed_l2_dispatch.add_argument("--prompt", required=True)
    typed_l2_dispatch.add_argument("--output", required=True)
    typed_l2_dispatch.add_argument("--run-id", required=True)
    typed_l2_dispatch.add_argument("--proposer-id", required=True)
    typed_l2_dispatch.add_argument("--proposer-version", required=True)
    typed_l2_dispatch.add_argument("--requested-model", required=True)
    typed_l2_dispatch.add_argument(
        "--isolation-context",
        required=True,
        choices=["fresh-agent-no-history-declarative"],
    )

    typed_l2_freeze = commands.add_parser(
        "freeze-typed-extractor-l2-proposals"
    )
    typed_l2_freeze.add_argument("--public", required=True)
    typed_l2_freeze.add_argument("--staged-proposals", required=True)
    typed_l2_freeze.add_argument("--output", required=True)
    typed_l2_freeze.add_argument("--provenance", required=True)
    typed_l2_freeze.add_argument("--prompt", required=True)
    typed_l2_freeze.add_argument("--dispatch", required=True)
    typed_l2_freeze.add_argument("--raw-response", required=True)
    typed_l2_freeze.add_argument(
        "--isolation-context",
        required=True,
        choices=["fresh-agent-no-history-declarative"],
    )

    typed_l2_score = commands.add_parser(
        "score-typed-extractor-l2-proposals"
    )
    typed_l2_score.add_argument("--root", required=True)
    typed_l2_score.add_argument("--proposals", required=True)
    typed_l2_score.add_argument("--provenance", required=True)
    typed_l2_score.add_argument("--guard-root", required=True)
    typed_l2_score.add_argument("--guard-slice-id", default="slice-v1")
    typed_l2_score.add_argument("--guard-results", required=True)
    typed_l2_score.add_argument("--output", required=True)
    typed_l2_score.add_argument("--report", required=True)
    typed_l2_score.add_argument("--error-analysis", required=True)

    freeze_typed_fresh = commands.add_parser(
        "freeze-typed-extractor-fresh-preregistration"
    )
    validate_typed_fresh = commands.add_parser(
        "validate-typed-extractor-fresh-preregistration"
    )
    for typed_fresh in (freeze_typed_fresh, validate_typed_fresh):
        typed_fresh.add_argument("--evaluation-root", required=True)
        typed_fresh.add_argument("--workspace-root", required=True)
        typed_fresh.add_argument("--bridge-ledger", required=True)
        typed_fresh.add_argument("--l1-prompt", required=True)
        typed_fresh.add_argument("--l2-prompt", required=True)
        typed_fresh.add_argument("--l1-dev-root", required=True)
        typed_fresh.add_argument("--l2-dev-root", required=True)
        typed_fresh.add_argument("--freeze-time", required=True)
    freeze_typed_fresh.add_argument("--output-root", required=True)
    validate_typed_fresh.add_argument("--root", required=True)

    freeze_typed_fresh_v2 = commands.add_parser(
        "freeze-typed-extractor-fresh-v2-preregistration"
    )
    validate_typed_fresh_v2 = commands.add_parser(
        "validate-typed-extractor-fresh-v2-preregistration"
    )
    for typed_fresh_v2 in (freeze_typed_fresh_v2, validate_typed_fresh_v2):
        typed_fresh_v2.add_argument("--evaluation-root", required=True)
        typed_fresh_v2.add_argument("--workspace-root", required=True)
        typed_fresh_v2.add_argument("--freeze-time", required=True)
    freeze_typed_fresh_v2.add_argument("--output-root", required=True)
    validate_typed_fresh_v2.add_argument("--root", required=True)

    freeze_typed_fresh_v3 = commands.add_parser(
        "freeze-typed-extractor-fresh-v3-preregistration"
    )
    validate_typed_fresh_v3 = commands.add_parser(
        "validate-typed-extractor-fresh-v3-preregistration"
    )
    for typed_fresh_v3 in (freeze_typed_fresh_v3, validate_typed_fresh_v3):
        typed_fresh_v3.add_argument("--evaluation-root", required=True)
        typed_fresh_v3.add_argument("--workspace-root", required=True)
        typed_fresh_v3.add_argument("--freeze-time", required=True)
    freeze_typed_fresh_v3.add_argument("--output-root", required=True)
    validate_typed_fresh_v3.add_argument("--root", required=True)

    keol_validate = commands.add_parser("validate-semantic-ir-keol-projection")
    keol_validate.add_argument("--projection", required=True)
    keol_validate.add_argument("--keol-root", required=True)
    keol_validate.add_argument("--output", required=True)
    keol_validate.add_argument("--root")
    keol_validate.add_argument("--slice-id", default="slice-v1")
    keol_validate.add_argument("--results")
    return parser


def _print(value: object) -> None:
    print(json.dumps(value, ensure_ascii=False, sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "freeze-slice":
        summary = freeze_slice_bundle(Path(args.raw_root), Path(args.root), args.slice_id)
        _print(summary)
        return 0
    if args.command == "validate-slice":
        summary = validate_slice_bundle(Path(args.root), args.slice_id)
        _print(summary)
        return 0
    if args.command == "validate-ledger":
        ledger = validate_external_results_ledger(Path(args.path))
        _print({"status": "valid", "entry_count": len(ledger.entries)})
        return 0
    if args.command == "run-identity-conformance":
        payload = run_identity_conformance_file(
            Path(args.root),
            Path(args.output),
            Path(args.report),
            run_id=args.run_id,
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(
            {
                "status": payload["status"],
                "run_id": payload["run_id"],
                "scenario_count": payload["scenario_count"],
            }
        )
        return 0
    if args.command == "freeze-natural-identity-slice":
        payload = freeze_natural_identity_slice(
            Path(args.source_config),
            Path(args.output_root),
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(payload)
        return 0
    if args.command == "validate-natural-identity-slice":
        payload = validate_natural_identity_slice(
            Path(args.root),
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(payload)
        return 0
    if args.command == "prepare-natural-identity-opaque-slice":
        payload = prepare_opaque_identity_slice(
            Path(args.v1_source),
            Path(args.output_root),
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(payload)
        return 0
    if args.command == "validate-natural-identity-opaque-slice":
        payload = validate_opaque_identity_slice(
            Path(args.v1_source),
            Path(args.root),
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(payload)
        return 0
    if args.command == "prepare-natural-identity-fresh-slice":
        payload = prepare_fresh_identity_slice(
            Path(args.v2_source),
            Path(args.hidden_source),
            Path(args.output_root),
            policy_freeze_path=Path(args.policy_freeze),
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(payload)
        return 0
    if args.command == "validate-natural-identity-fresh-slice":
        payload = validate_fresh_identity_slice(
            Path(args.v2_source),
            Path(args.hidden_source),
            Path(args.root),
            policy_freeze_path=Path(args.policy_freeze),
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(payload)
        return 0
    if args.command == "prepare-identity-dev-slice":
        payload = prepare_identity_dev_slice(
            Path(args.v2_source),
            Path(args.output_root),
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(payload)
        return 0
    if args.command == "freeze-identity-proposer-policy":
        payload = freeze_identity_proposer_policy(
            Path(args.policy),
            Path(args.dev_prompt),
            Path(args.final_prompt),
            Path(args.output),
            dev_public_path=Path(args.dev_public),
            final_public_path=Path(args.final_public),
            dev_run_id=args.dev_run_id,
            final_run_id=args.final_run_id,
            proposer_id=args.proposer_id,
            proposer_version=args.proposer_version,
            dev_dataset_id=args.dev_dataset_id,
            dev_case_count=args.dev_case_count,
            final_case_count=args.final_case_count,
        )
        _print(payload)
        return 0
    if args.command == "prepare-identity-model-dispatch":
        payload = write_identity_model_dispatch(
            Path(args.public),
            Path(args.prompt),
            Path(args.output),
            run_id=args.run_id,
            proposer_id=args.proposer_id,
            proposer_version=args.proposer_version,
            isolation_context=args.isolation_context,
        )
        _print(payload)
        return 0
    if args.command == "freeze-identity-model-proposals":
        payload = freeze_identity_model_proposals(
            Path(args.public),
            Path(args.staged_proposals),
            Path(args.output),
            Path(args.provenance),
            prompt_path=Path(args.prompt),
            dispatch_path=Path(args.dispatch),
            isolation_context=args.isolation_context,
        )
        _print(payload)
        return 0
    if args.command == "run-identity-proposal-reference":
        payload = run_reference_identity_proposer_file(
            Path(args.public),
            Path(args.output),
            run_id=args.run_id,
        )
        _print(
            {
                "status": "valid",
                "run_id": payload["run_id"],
                "case_count": payload["case_count"],
            }
        )
        return 0
    if args.command == "score-identity-proposals":
        payload = score_identity_proposals_file(
            Path(args.root),
            Path(args.proposals),
            Path(args.output),
            Path(args.report),
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        _print(
            {
                "status": payload["status"],
                "run_id": payload["run_id"],
                "case_count": payload["case_count"],
                "gate_safety_ready": payload["gate_safety_ready"],
                "proposal_quality_ready": payload["proposal_quality_ready"],
            }
        )
        return 0
    if args.command == "assess-identity-candidate-generation":
        payload = run_identity_candidate_assessment_file(
            Path(args.public),
            Path(args.proposals),
            Path(args.score),
            Path(args.experiment_root),
            args.guard_scenario_id,
            Path(args.queue),
            Path(args.output),
            Path(args.report),
        )
        _print(
            {
                "status": payload["status"],
                "case_count": payload["case_count"],
                "raw_proposer_quality_ready": payload[
                    "raw_proposer_quality_ready"
                ],
                "deterministic_gate_safety_ready": payload[
                    "deterministic_gate_safety_ready"
                ],
                "candidate_generation_integration_ready": payload[
                    "candidate_generation_integration_ready"
                ],
                "automatic_authoritative_write_count": payload["metrics"][
                    "automatic_authoritative_write_count"
                ],
            }
        )
        return 0
    if args.command == "assess-automatic-l1-l2-extraction":
        payload = run_extraction_bridge_assessment(
            source_path=Path(args.source),
            turn_manifest_path=Path(args.turn_manifest),
            dialogue_manifest_path=Path(args.dialogue_manifest),
            final_knowledge_path=Path(args.final_knowledge),
            run_path=Path(args.run),
            source_segments_path=Path(args.source_segments),
            guard_root=Path(args.guard_root),
            guard_slice_id=args.guard_slice_id,
            guard_results_path=Path(args.guard_results),
            ledger_path=Path(args.ledger),
            assessment_path=Path(args.output),
            report_path=Path(args.report),
        )
        _print(payload)
        return 0
    if args.command == "prepare-typed-extractor-l1-dev":
        payload = prepare_l1_dev_slice(
            source_config_path=Path(args.source_config),
            prompt_path=Path(args.prompt),
            bridge_ledger_path=Path(args.bridge_ledger),
            source_path=Path(args.source),
            turn_manifest_path=Path(args.turn_manifest),
            dialogue_manifest_path=Path(args.dialogue_manifest),
            final_knowledge_path=Path(args.final_knowledge),
            run_path=Path(args.run),
            source_segments_path=Path(args.source_segments),
            output_root=Path(args.output_root),
        )
        _print(payload)
        return 0
    if args.command == "validate-typed-extractor-l1-dev":
        payload = validate_l1_dev_slice(
            source_config_path=Path(args.source_config),
            prompt_path=Path(args.prompt),
            bridge_ledger_path=Path(args.bridge_ledger),
            source_path=Path(args.source),
            turn_manifest_path=Path(args.turn_manifest),
            dialogue_manifest_path=Path(args.dialogue_manifest),
            final_knowledge_path=Path(args.final_knowledge),
            run_path=Path(args.run),
            source_segments_path=Path(args.source_segments),
            root=Path(args.root),
        )
        _print(payload)
        return 0
    if args.command in {
        "prepare-typed-extractor-l1-dev-repair",
        "validate-typed-extractor-l1-dev-repair",
    }:
        target = Path(args.output_root) if hasattr(args, "output_root") else Path(args.root)
        function = (
            prepare_l1_dev_repair_slice
            if args.command.startswith("prepare-")
            else validate_l1_dev_repair_slice
        )
        payload = function(
            Path(args.source),
            target,
            [Path(item) for item in args.prior_root],
        )
        _print(
            {
                "status": payload["status"],
                "case_count": payload["case_count"],
                "provenance": payload["provenance"],
            }
        )
        return 0
    if args.command == "prepare-typed-extractor-l1-dispatch":
        payload = write_l1_model_dispatch(
            Path(args.public),
            Path(args.prompt),
            Path(args.output),
            run_id=args.run_id,
            proposer_id=args.proposer_id,
            proposer_version=args.proposer_version,
            requested_model=args.requested_model,
            isolation_context=args.isolation_context,
        )
        _print(payload)
        return 0
    if args.command == "freeze-typed-extractor-l1-proposals":
        payload = freeze_l1_model_proposals(
            Path(args.public),
            Path(args.staged_proposals),
            Path(args.output),
            Path(args.provenance),
            prompt_path=Path(args.prompt),
            dispatch_path=Path(args.dispatch),
            raw_response_path=Path(args.raw_response),
            isolation_context=args.isolation_context,
        )
        _print(payload)
        return 0
    if args.command == "score-typed-extractor-l1-proposals":
        payload = run_l1_scoring_file(
            Path(args.root),
            Path(args.proposals),
            Path(args.provenance),
            guard_root=Path(args.guard_root),
            guard_slice_id=args.guard_slice_id,
            guard_results_path=Path(args.guard_results),
            score_path=Path(args.output),
            report_path=Path(args.report),
            error_analysis_path=Path(args.error_analysis),
        )
        _print(
            {
                "status": payload["status"],
                "run_id": payload["run_id"],
                "case_count": payload["case_count"],
                "raw_proposer_quality_ready": payload[
                    "raw_proposer_quality_ready"
                ],
                "deterministic_gate_safety_ready": payload[
                    "deterministic_gate_safety_ready"
                ],
            }
        )
        return 0
    if args.command == "prepare-typed-extractor-l2-dev":
        payload = prepare_l2_dev_slice(
            source_config_path=Path(args.source_config),
            prompt_path=Path(args.prompt),
            bridge_ledger_path=Path(args.bridge_ledger),
            source_path=Path(args.source),
            turn_manifest_path=Path(args.turn_manifest),
            dialogue_manifest_path=Path(args.dialogue_manifest),
            final_knowledge_path=Path(args.final_knowledge),
            run_path=Path(args.run),
            source_segments_path=Path(args.source_segments),
            l1_qualification_root=Path(args.l1_qualification_root),
            output_root=Path(args.output_root),
        )
        _print(payload)
        return 0
    if args.command == "validate-typed-extractor-l2-dev":
        payload = validate_l2_dev_slice(
            source_config_path=Path(args.source_config),
            prompt_path=Path(args.prompt),
            bridge_ledger_path=Path(args.bridge_ledger),
            source_path=Path(args.source),
            turn_manifest_path=Path(args.turn_manifest),
            dialogue_manifest_path=Path(args.dialogue_manifest),
            final_knowledge_path=Path(args.final_knowledge),
            run_path=Path(args.run),
            source_segments_path=Path(args.source_segments),
            l1_qualification_root=Path(args.l1_qualification_root),
            root=Path(args.root),
        )
        _print(payload)
        return 0
    if args.command in {
        "prepare-typed-extractor-l2-dev-repair",
        "validate-typed-extractor-l2-dev-repair",
    }:
        target = Path(args.output_root) if hasattr(args, "output_root") else Path(args.root)
        function = (
            prepare_l2_dev_repair_slice
            if args.command.startswith("prepare-")
            else validate_l2_dev_repair_slice
        )
        payload = function(
            Path(args.source),
            target,
            [Path(item) for item in args.prior_root],
        )
        _print(
            {
                "status": payload["status"],
                "case_count": payload["case_count"],
                "provenance": payload["provenance"],
            }
        )
        return 0
    if args.command == "qualify-typed-extractor-dev-repair":
        payload = qualify_dev_repair(
            args.layer,
            Path(args.score),
            Path(args.output),
            Path(args.report),
        )
        _print(
            {
                "status": payload["status"],
                "layer": payload["layer"],
                "dataset_id": payload["dataset_id"],
                "run_id": payload["run_id"],
                "raw_proposer_quality_ready": payload[
                    "raw_proposer_quality_ready"
                ],
                "deterministic_gate_safety_ready": payload[
                    "deterministic_gate_safety_ready"
                ],
                "dev_repair_ready": payload["dev_repair_ready"],
            }
        )
        return 0
    if args.command == "prepare-typed-extractor-l2-dispatch":
        payload = write_l2_model_dispatch(
            Path(args.public),
            Path(args.prompt),
            Path(args.output),
            run_id=args.run_id,
            proposer_id=args.proposer_id,
            proposer_version=args.proposer_version,
            requested_model=args.requested_model,
            isolation_context=args.isolation_context,
        )
        _print(payload)
        return 0
    if args.command == "freeze-typed-extractor-l2-proposals":
        payload = freeze_l2_model_proposals(
            Path(args.public),
            Path(args.staged_proposals),
            Path(args.output),
            Path(args.provenance),
            prompt_path=Path(args.prompt),
            dispatch_path=Path(args.dispatch),
            raw_response_path=Path(args.raw_response),
            isolation_context=args.isolation_context,
        )
        _print(payload)
        return 0
    if args.command == "score-typed-extractor-l2-proposals":
        payload = run_l2_scoring_file(
            Path(args.root),
            Path(args.proposals),
            Path(args.provenance),
            guard_root=Path(args.guard_root),
            guard_slice_id=args.guard_slice_id,
            guard_results_path=Path(args.guard_results),
            score_path=Path(args.output),
            report_path=Path(args.report),
            error_analysis_path=Path(args.error_analysis),
        )
        _print(
            {
                "status": payload["status"],
                "run_id": payload["run_id"],
                "case_count": payload["case_count"],
                "raw_proposer_quality_ready": payload[
                    "raw_proposer_quality_ready"
                ],
                "deterministic_gate_safety_ready": payload[
                    "deterministic_gate_safety_ready"
                ],
            }
        )
        return 0
    if args.command == "freeze-typed-extractor-fresh-preregistration":
        payload = freeze_typed_extractor_fresh_preregistration(
            output_root=Path(args.output_root),
            evaluation_root=Path(args.evaluation_root),
            workspace_root=Path(args.workspace_root),
            bridge_ledger_path=Path(args.bridge_ledger),
            l1_prompt_path=Path(args.l1_prompt),
            l2_prompt_path=Path(args.l2_prompt),
            l1_dev_root=Path(args.l1_dev_root),
            l2_dev_root=Path(args.l2_dev_root),
            freeze_time=args.freeze_time,
        )
        _print(
            {
                "status": payload["status"],
                "evaluation_id": payload["evaluation_id"],
                "l1_case_count": payload["selection"]["l1_case_count"],
                "l2_case_count": payload["selection"]["l2_case_count"],
            }
        )
        return 0
    if args.command == "validate-typed-extractor-fresh-preregistration":
        payload = validate_typed_extractor_fresh_preregistration(
            root=Path(args.root),
            evaluation_root=Path(args.evaluation_root),
            workspace_root=Path(args.workspace_root),
            bridge_ledger_path=Path(args.bridge_ledger),
            l1_prompt_path=Path(args.l1_prompt),
            l2_prompt_path=Path(args.l2_prompt),
            l1_dev_root=Path(args.l1_dev_root),
            l2_dev_root=Path(args.l2_dev_root),
            freeze_time=args.freeze_time,
        )
        _print(payload)
        return 0
    if args.command == "freeze-typed-extractor-fresh-v2-preregistration":
        payload = freeze_typed_extractor_fresh_v2_preregistration(
            output_root=Path(args.output_root),
            evaluation_root=Path(args.evaluation_root),
            workspace_root=Path(args.workspace_root),
            freeze_time=args.freeze_time,
        )
        _print(
            {
                "status": payload["status"],
                "evaluation_id": payload["evaluation_id"],
                "l1_case_count": payload["authorship"]["l1_case_count"],
                "l2_case_count": payload["authorship"]["l2_case_count"],
            }
        )
        return 0
    if args.command == "validate-typed-extractor-fresh-v2-preregistration":
        payload = validate_typed_extractor_fresh_v2_preregistration(
            root=Path(args.root),
            evaluation_root=Path(args.evaluation_root),
            workspace_root=Path(args.workspace_root),
            freeze_time=args.freeze_time,
        )
        _print(payload)
        return 0
    if args.command == "freeze-typed-extractor-fresh-v3-preregistration":
        payload = freeze_typed_extractor_fresh_v3_preregistration(
            output_root=Path(args.output_root),
            evaluation_root=Path(args.evaluation_root),
            workspace_root=Path(args.workspace_root),
            freeze_time=args.freeze_time,
        )
        _print(
            {
                "status": payload["status"],
                "evaluation_id": payload["evaluation_id"],
                "l1_case_count": payload["authorship"]["l1_case_count"],
                "l2_case_count": payload["authorship"]["l2_case_count"],
            }
        )
        return 0
    if args.command == "validate-typed-extractor-fresh-v3-preregistration":
        payload = validate_typed_extractor_fresh_v3_preregistration(
            root=Path(args.root),
            evaluation_root=Path(args.evaluation_root),
            workspace_root=Path(args.workspace_root),
            freeze_time=args.freeze_time,
        )
        _print(payload)
        return 0
    if args.command == "score-results":
        report = score_results_file(Path(args.root), args.slice_id, Path(args.results), Path(args.output))
        _print(
            {
                "status": "valid",
                "run_id": report.run_id,
                "slice_id": report.slice_id,
                "arm": report.arm,
                "item_count": report.metrics["item_count"],
            }
        )
        return 0
    if args.command == "export-gold-evidence":
        payload = export_gold_evidence_file(Path(args.root), args.slice_id, Path(args.output))
        _print({"status": "valid", "slice_id": payload["slice_id"], "item_count": payload["item_count"]})
        return 0
    if args.command == "export-evidence-corpus":
        payload = export_evidence_corpus_file(Path(args.root), args.slice_id, Path(args.output))
        _print({"status": "valid", "slice_id": payload["slice_id"], "item_count": payload["item_count"]})
        return 0
    if args.command == "run-dense-reference":
        payload = run_dense_reference_file(
            Path(args.slice),
            Path(args.corpus),
            Path(args.output),
            run_id=args.run_id,
            top_k=args.top_k,
            encoder_name=args.encoder,
        )
        _print({"status": "valid", "run_id": payload["run_id"], "item_count": len(payload["items"])})
        return 0
    if args.command == "run-symbolic":
        payload = run_symbolic_file(
            Path(args.slice),
            Path(args.corpus),
            Path(args.output),
            run_id=args.run_id,
            top_k=args.top_k,
        )
        _print({"status": "valid", "run_id": payload["run_id"], "item_count": len(payload["items"])})
        return 0
    if args.command == "run-symbolic-fallback":
        payload = run_symbolic_fallback_file(
            Path(args.slice),
            Path(args.corpus),
            Path(args.output),
            run_id=args.run_id,
            symbolic_top_k=args.symbolic_top_k,
            fallback_top_k=args.fallback_top_k,
            encoder_name=args.encoder,
        )
        _print({"status": "valid", "run_id": payload["run_id"], "item_count": len(payload["items"])})
        return 0
    if args.command == "run-semantic-ir-diagnostics":
        payload = run_semantic_ir_diagnostics_file(
            Path(args.output),
            Path(args.report),
            run_id=args.run_id,
        )
        _print(
            {
                "status": "valid",
                "run_id": payload["run_id"],
                "case_count": payload["metrics"]["case_count"],
                "pass_count": payload["metrics"]["pass_count"],
            }
        )
        return 0
    if args.command == "run-semantic-ir-slice-diagnostics":
        payload = run_real_slice_semantic_ir_diagnostics_file(
            Path(args.root),
            args.slice_id,
            Path(args.results),
            Path(args.output),
            Path(args.report),
            run_id=args.run_id,
        )
        _print(
            {
                "status": "valid",
                "run_id": payload["run_id"],
                "case_count": payload["metrics"]["case_count"],
                "pass_count": payload["metrics"]["pass_count"],
            }
        )
        return 0
    if args.command == "project-semantic-ir-slice-to-keol":
        payload = project_semantic_ir_slice_suite_to_keol_file(
            Path(args.root),
            args.slice_id,
            Path(args.results),
            Path(args.output),
            workflow_run_id=args.workflow_run_id,
        )
        _print(
            {
                "status": "valid",
                "workflow_run_id": args.workflow_run_id,
                "assertion_count": len(payload["assertions"]),
                "evidence_count": len(payload["evidence"]),
            }
        )
        return 0
    if args.command == "trace-semantic-ir-keol-projection":
        payload = write_projection_trace_report(
            Path(args.projection),
            Path(args.output),
            Path(args.report),
        )
        _print(
            {
                "status": "valid",
                "assertion_count": payload["metrics"]["assertion_count"],
                "broken_evidence_ref_count": payload["metrics"]["broken_evidence_ref_count"],
            }
        )
        return 0
    if args.command == "run-representation-conformance":
        payload = run_representation_conformance_file(
            Path(args.root),
            args.slice_id,
            Path(args.results),
            Path(args.output),
            Path(args.report),
            run_id=args.run_id,
        )
        report = payload["reference_carrier"]
        _print(
            {
                "status": "valid",
                "run_id": payload["run_id"],
                "round_trip_exact": report["round_trip_exact"],
                "query_probe_pass_count": report["query_probe_pass_count"],
            }
        )
        return 0
    if args.command == "run-authoritative-conformance":
        payload = run_authoritative_conformance_file(
            Path(args.root),
            args.slice_id,
            Path(args.results),
            Path(args.output),
            Path(args.report),
            run_id=args.run_id,
            workspace_root=Path(args.workspace_root) if args.workspace_root else None,
        )
        reference = payload["reference_carrier"]
        _print(
            {
                "status": "valid",
                "run_id": payload["run_id"],
                "source_validation_valid": payload["source_validation"]["valid"],
                "round_trip_exact": reference["round_trip_exact"],
                "query_probe_pass_count": reference["query_probe_pass_count"],
                "correctness_pass_count": reference["correctness_pass_count"],
            }
        )
        return 0
    if args.command == "validate-semantic-ir-keol-projection":
        payload = validate_keol_projection_file(
            Path(args.projection),
            Path(args.keol_root),
            Path(args.output),
            root=Path(args.root) if args.root else None,
            slice_id=args.slice_id if args.root else None,
            results_path=Path(args.results) if args.results else None,
        )
        _print(
            {
                "status": "valid",
                "classification": payload["classification"],
                "native_model_error_count": payload["native_model_error_count"],
                "closure_parity_mismatch_count": payload["closure_parity"]["mismatch_count"],
            }
        )
        return 0
    raise NotImplementedError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
