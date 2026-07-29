from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_workspace_files_are_grouped_by_responsibility() -> None:
    expected_files = [
        "README.md",
        "data/gold-candidates/KE-test.json",
        "data/gold-candidates/KE-test-config.md",
        "docs/reference/memory实现方案汇报.pdf",
        "tools/keol_baseline/keol_ke_test_adapter.py",
        "tools/keol_baseline/run_keol_pipeline.py",
        "tools/keol_baseline/export_keol_views.py",
        "artifacts/keol-baseline/views/KE.txt",
        "artifacts/keol-baseline/views/KE-extraction.json",
        "artifacts/keol-baseline/views/KE-ontology.json",
        "artifacts/keol-baseline/run/KEOL-run.json",
        "archive/legacy-ke-v0.2/build_ke_experiment.mjs",
        "archive/legacy-ke-v0.2/validate_ke_experiment.mjs",
        "archive/legacy-ke-v0.2/ke-runtime.mjs",
        "archive/legacy-ke-v0.2/ke-specs.mjs",
        "tools/amr_pilot/cli.py",
        "tools/amr_pilot/payloads.py",
        "tools/amr_pilot/penman_validation.py",
        "tools/amr_pilot/run_ledger.py",
        "tools/amr_pilot/scoring.py",
        "tools/amr_pilot/report.py",
        "tools/amr_pilot/requirements.txt",
        "artifacts/amr-pilot/prompts/direct-amr-v1.md",
        "artifacts/amr-pilot/prompts/atomic-knowledge-v1.md",
        "artifacts/amr-pilot/prompts/knowledge-to-amr-v1.md",
        "tools/ontology_memory_experiment/cli.py",
        "tools/ontology_memory_experiment/models.py",
        "tools/ontology_memory_experiment/scenarios.py",
        "tools/ontology_memory_experiment/representations.py",
        "tools/ontology_memory_experiment/executors.py",
        "tools/ontology_memory_experiment/scoring.py",
        "tools/ontology_memory_experiment/report.py",
        "artifacts/ontology-memory-experiment/architecture-audit/source-manifest.json",
        "artifacts/ontology-memory-experiment/architecture-audit/capability-matrix.json",
        "artifacts/ontology-memory-experiment/architecture-audit/gap-hypothesis-ledger.json",
        "artifacts/ontology-memory-experiment/architecture-audit/official-results-ledger.json",
        "artifacts/ontology-memory-experiment/gold/source-scenarios.json",
        "artifacts/ontology-memory-experiment/gold/gold.json",
        "artifacts/ontology-memory-experiment/gold/distractors.json",
        "artifacts/ontology-memory-experiment/gold/oracle-representations.json",
        "artifacts/ontology-memory-experiment/gold/oracle-query-plans.json",
        "artifacts/ontology-memory-experiment/gold/manifest.json",
    ]
    missing = [path for path in expected_files if not (ROOT / path).is_file()]
    assert missing == []


def test_generated_and_legacy_files_do_not_clutter_the_workspace_root() -> None:
    root_clutter = [
        "KE-test.json",
        "KE-test-config.md",
        "memory实现方案汇报.pdf",
        "keol_ke_test_adapter.py",
        "run_keol_pipeline.py",
        "export_keol_views.py",
        "KE.txt",
        "KE-extraction.json",
        "KE-ontology.json",
        "KEOL-run.json",
        "build_ke_experiment.mjs",
        "validate_ke_experiment.mjs",
        "ke-runtime.mjs",
        "ke-specs.mjs",
    ]
    remaining = [path for path in root_clutter if (ROOT / path).exists()]
    assert remaining == []


def test_active_knowledge_artifacts_remain_in_their_audited_location() -> None:
    active_artifacts = [
        "knowledge-extraction/KE-knowledge-keywords.json",
        "knowledge-extraction/keyword-v3-preview-lawyer-leave.json",
        "knowledge-extraction/keyword-pass-v3/keyword-pass.json",
        "knowledge-extraction/run.json",
        "knowledge-extraction/knowledge-extraction-prompt-and-strategy.md",
    ]
    missing = [path for path in active_artifacts if not (ROOT / path).is_file()]
    assert missing == []
