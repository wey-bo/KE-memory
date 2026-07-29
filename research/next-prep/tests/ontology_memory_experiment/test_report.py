from tools.ontology_memory_experiment.report import build_gate_report


def _arm(exact, cfpr, recall=1.0, *, cfp_denominator=10):
    return {
        "overall": {
            "evidence_set_exact_match": exact,
            "critical_false_positive_rate": cfpr,
            "critical_false_positive_denominator": cfp_denominator,
            "recall_at_k": recall,
        },
        "families": {
            "roles_polarity_modality_quantity": {"evidence_set_exact_match": exact},
            "temporal_updates_conflicts_provenance": {"evidence_set_exact_match": exact},
            "conjunction_exact_set_multihop": {"evidence_set_exact_match": exact},
            "lexical": {"recall_at_k": recall},
            "out_of_domain": {"recall_at_k": recall},
        },
        "scales": {"500": {"evidence_set_exact_match": exact}},
    }


def _passing_metrics():
    return {
        "arms": {
            "oracle": {
                "B0": _arm(.50, .30),
                "B1": _arm(.52, .30),
                "B2": _arm(.54, .30),
                "O-": _arm(.50, .30),
                "O+": _arm(.75, .10),
                "O+E": _arm(.75, .10, .98),
            },
            "automatic": {
                "B0": _arm(.50, .30),
                "B1": _arm(.52, .30),
                "B2": _arm(.54, .30),
                "O+": _arm(.70, .10),
                "O+E": _arm(.70, .10, .98),
            },
        },
        "fallback": {"overall_rate": .20, "structural_family_rate": .05},
    }


def test_gate_report_requires_all_six_approved_conditions_and_returns_pass():
    metrics = _passing_metrics()

    report = build_gate_report(metrics)

    assert report["decision"] == "pass"
    assert len(report["gates"]) == 6
    assert all(gate["status"] == "pass" for gate in report["gates"])
    assert report["strong_dense_baseline"] == "B2"


def test_gate_report_is_undecidable_when_required_dense_or_automatic_evidence_is_missing():
    report = build_gate_report({"arms": {"oracle": {}}, "fallback": {}})

    assert report["decision"] == "undecidable"


def test_gate_report_is_undecidable_when_critical_fp_baseline_has_zero_denominator():
    metrics = _passing_metrics()
    metrics["arms"]["oracle"]["B2"] = _arm(.54, 0, cfp_denominator=0)

    report = build_gate_report(metrics)

    assert report["decision"] == "undecidable"
    statuses = {gate["name"]: gate["status"] for gate in report["gates"]}
    assert statuses["critical_false_positive_reduction"] == "undecidable"
    assert all(status == "pass" for name, status in statuses.items() if name != "critical_false_positive_reduction")


def test_gate_report_compares_every_structural_gain_to_same_best_dense_arm():
    metrics = _passing_metrics()
    metrics["arms"]["oracle"]["B2"] = _arm(.75, .30)
    metrics["arms"]["automatic"]["B2"] = _arm(.70, .30)

    report = build_gate_report(metrics)

    assert report["strong_dense_baseline"] == "B2"
    assert report["decision"] == "fail"
    statuses = {gate["name"]: gate["status"] for gate in report["gates"]}
    assert statuses["structural_exact_match"] == "fail"
    assert statuses["distractor_500"] == "fail"
    assert statuses["automatic_retained_gain"] == "undecidable"


def test_gate_report_requires_all_three_dense_arms_before_selecting_baseline():
    metrics = _passing_metrics()
    del metrics["arms"]["oracle"]["B1"]

    report = build_gate_report(metrics)

    assert report["strong_dense_baseline"] is None
    statuses = {gate["name"]: gate["status"] for gate in report["gates"]}
    assert statuses["structural_exact_match"] == "undecidable"
    assert statuses["critical_false_positive_reduction"] == "undecidable"
    assert statuses["distractor_500"] == "undecidable"
    assert statuses["automatic_retained_gain"] == "undecidable"
    assert statuses["fallback_limits"] == "pass"


def test_gate_report_marks_only_error_contaminated_comparisons_undecidable():
    metrics = _passing_metrics()
    metrics["arms"]["oracle"]["B2"]["overall"].update(
        evidence_set_exact_match=None,
        execution_error_count=1,
        comparison_eligible=False,
    )

    report = build_gate_report(metrics)

    statuses = {gate["name"]: gate["status"] for gate in report["gates"]}
    assert statuses["fallback_limits"] == "pass"
    assert statuses["lexical_recall"] == "undecidable"
    assert report["decision"] == "undecidable"
