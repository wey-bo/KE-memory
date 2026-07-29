from tools.ontology_memory_experiment.scoring import aggregate_metrics, paired_bootstrap_interval


def test_aggregate_metrics_groups_scales_by_base_scenario_and_calculates_evidence_and_constraint_metrics():
    results = [
        {"scenario_id": "S1", "distractor_scale": 0, "arm": "O+", "track": "oracle", "selected_evidence_turn_ids": ["T1"], "predicted_answer": "Avery", "constraint_checks": {"roles": True}, "fallback_trigger": None, "latency_ms": 4},
        {"scenario_id": "S1", "distractor_scale": 500, "arm": "O+", "track": "oracle", "selected_evidence_turn_ids": ["T1"], "predicted_answer": "Avery", "constraint_checks": {"roles": True}, "fallback_trigger": None, "latency_ms": 6},
    ]
    gold = {"S1": {"required_evidence_turn_ids": ["T1"], "hard_negative_turn_ids": ["T2"], "answer": {"kind": "value", "values": ["Avery"]}}}

    metrics = aggregate_metrics(results, gold)

    overall = metrics["arms"]["oracle"]["O+"]["overall"]
    assert overall["base_scenarios"] == 1
    assert overall["evidence_set_exact_match"] == 1.0
    assert overall["constraint_satisfaction_rate"] == 1.0
    assert overall["latency_p50_ms"] == 5.0


def test_paired_bootstrap_samples_base_scenarios_not_distractor_rows():
    interval = paired_bootstrap_interval({"S1": 0.2, "S2": 0.4}, iterations=200, seed=7)

    assert interval["point_estimate"] == 0.3
    assert interval["unit"] == "base_scenario"


def test_aggregate_metrics_emits_family_scale_fallback_and_normalized_unanswerable_metrics():
    results = [{"scenario_id": "S2", "distractor_scale": 500, "arm": "O+E", "track": "automatic", "selected_evidence_turn_ids": ["T2"], "predicted_answer": None, "abstained": True, "constraint_checks": {"polarity": True}, "fallback": {"triggered": True, "reason": "uncovered_predicate"}, "latency_ms": 2}]
    gold = {"S2": {"family": "synonymy_sense_external_unanswerable", "required_evidence_turn_ids": ["T2"], "hard_negative_turn_ids": ["T9"], "answer": {"kind": "unanswerable", "values": []}}}

    metrics = aggregate_metrics(results, gold)

    arm = metrics["arms"]["automatic"]["O+E"]
    assert arm["families"]["synonymy_sense_external_unanswerable"]["abstention_accuracy"] == 1.0
    assert arm["scales"]["500"]["fallback_rate"] == 1.0
    assert metrics["fallback"]["overall_rate"] == 1.0


def test_aggregate_metrics_populates_paired_bootstrap_and_limits_fallback_denominator_to_ope():
    results = [
        {"scenario_id": "S3", "distractor_scale": 500, "arm": "B0", "track": "oracle", "selected_evidence_turn_ids": [], "constraint_checks": {}, "fallback": {"triggered": True}},
        {"scenario_id": "S3", "distractor_scale": 500, "arm": "O-", "track": "oracle", "selected_evidence_turn_ids": [], "constraint_checks": {}, "fallback": {"triggered": True}},
        {"scenario_id": "S3", "distractor_scale": 500, "arm": "O+", "track": "oracle", "selected_evidence_turn_ids": ["T3"], "constraint_checks": {"complete_result": True}, "fallback": {"triggered": False}},
        {"scenario_id": "S3", "distractor_scale": 500, "arm": "O+E", "track": "automatic", "selected_evidence_turn_ids": ["T3"], "constraint_checks": {"complete_result": True}, "fallback": {"triggered": True}},
    ]
    gold = {"S3": {"family": "roles_polarity_modality_quantity", "required_evidence_turn_ids": ["T3"], "hard_negative_turn_ids": ["T9"], "answer": {"kind": "value", "values": ["Avery"]}}}

    metrics = aggregate_metrics(results, gold)

    assert metrics["bootstrap"]["overall"]["O+_minus_B0"]["point_estimate"] == 1.0
    assert metrics["bootstrap"]["scale_500"]["O+_minus_O-"]["point_estimate"] == 1.0
    assert metrics["fallback"]["overall_rate"] == 1.0


def test_error_rows_never_receive_abstention_credit_and_contaminate_required_comparisons():
    results = [
        {
            "scenario_id": "S4",
            "distractor_scale": 500,
            "arm": "O+",
            "track": "oracle",
            "selected_evidence_turn_ids": [],
            "predicted_answer": None,
            "abstained": True,
            "error": "RuntimeError: failed",
        },
        {
            "scenario_id": "S4",
            "distractor_scale": 500,
            "arm": "B0",
            "track": "oracle",
            "selected_evidence_turn_ids": [],
            "predicted_answer": None,
            "abstained": True,
        },
    ]
    gold = {
        "S4": {
            "family": "synonymy_sense_external_unanswerable",
            "required_evidence_turn_ids": [],
            "hard_negative_turn_ids": ["T9"],
            "answer": {"kind": "unanswerable", "values": []},
        }
    }

    metrics = aggregate_metrics(results, gold)

    oplus = metrics["arms"]["oracle"]["O+"]["overall"]
    assert oplus["answer_correctness"] is None
    assert oplus["abstention_accuracy"] is None
    assert oplus["execution_error_count"] == 1
    assert oplus["comparison_eligible"] is False
    comparison = metrics["bootstrap"]["overall"]["O+_minus_B0"]
    assert comparison["point_estimate"] is None
    assert comparison["contaminated_base_scenarios"] == ["S4"]


def test_aggregate_metrics_uses_caller_bootstrap_seed():
    results = [
        {"scenario_id": "S5", "arm": arm, "track": "oracle", "selected_evidence_turn_ids": ["T5"]}
        for arm in ("B0", "O-", "O+")
    ]
    gold = {
        "S5": {
            "required_evidence_turn_ids": ["T5"],
            "hard_negative_turn_ids": ["T9"],
            "answer": {"kind": "value", "values": ["answer"]},
        }
    }

    metrics = aggregate_metrics(results, gold, bootstrap_seed=19)

    assert metrics["bootstrap"]["overall"]["O+_minus_B0"]["seed"] == 19
    assert metrics["bootstrap"]["scale_500"]["O+_minus_O-"]["seed"] == 19


def test_unavailable_extraction_accuracy_remains_null_at_every_summary_level():
    results = [
        {"scenario_id": "S6", "arm": "O+", "track": "automatic", "selected_evidence_turn_ids": ["T6"]}
    ]
    gold = {
        "S6": {
            "family": "roles_polarity_modality_quantity",
            "required_evidence_turn_ids": ["T6"],
            "hard_negative_turn_ids": ["T9"],
            "answer": {"kind": "value", "values": ["answer"]},
        }
    }

    metrics = aggregate_metrics(results, gold)

    arm = metrics["arms"]["automatic"]["O+"]
    assert arm["by_base_scenario"][0]["extraction_accuracy"] is None
    assert arm["overall"]["extraction_accuracy"] is None
    assert arm["families"]["roles_polarity_modality_quantity"]["extraction_accuracy"] is None


def test_critical_false_positives_include_caller_supplied_distractor_ids():
    results = [
        {
            "scenario_id": "S7",
            "arm": "O+",
            "track": "oracle",
            "selected_evidence_turn_ids": ["T7", "D7-critical"],
        }
    ]
    gold = {
        "S7": {
            "required_evidence_turn_ids": ["T7"],
            "hard_negative_turn_ids": ["T9"],
            "answer": {"kind": "value", "values": ["answer"]},
        }
    }

    metrics = aggregate_metrics(
        results,
        gold,
        critical_distractor_ids={"S7": ["D7-critical"]},
    )

    overall = metrics["arms"]["oracle"]["O+"]["overall"]
    assert overall["critical_false_positive_rate"] == 1.0
    assert overall["critical_false_positive_denominator"] == 1
