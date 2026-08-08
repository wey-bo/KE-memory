#!/usr/bin/env python3
"""Regression tests for the non-production Canonical Text reference harness."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "docs" / "specifications" / "memory-assertion-v1"
SCHEMA_DIR = SPEC / "schema"
FIXTURE = ROOT / "fixtures" / "ontology-snapshot-example"
TOOLS = ROOT / "tools"
sys.path.insert(0, str(TOOLS))

from canonical_text_reference import CanonicalTextError, ReferenceEnvironment  # noqa: E402 - requires the sys.path insert above


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def jcs_text(value: Any) -> str:
    node = shutil.which("node")
    if node is None:
        raise RuntimeError("Node.js is required for Canonical Text tests")
    completed = subprocess.run(
        [node, str(TOOLS / "jcs.mjs")],
        input=json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.decode("utf-8", errors="replace"))
    return completed.stdout.decode("utf-8")


class CanonicalTextReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.vectors = read_json(SCHEMA_DIR / "canonical-text-reference-vectors.json")
        cls.examples = read_json(SCHEMA_DIR / "examples.json")
        environment = cls.vectors["environment"]
        manifest = read_json(
            (SCHEMA_DIR / environment["snapshot_fixture_path"]).resolve()
        )
        cls.snapshot_ref = {
            "snapshot_id": manifest["snapshot_id"],
            "sha256": manifest["sha256"],
        }
        cls.reference = ReferenceEnvironment(
            snapshot_ref=cls.snapshot_ref,
            concepts=read_json(FIXTURE / "concepts" / "core.json")["concepts"],
            operators=read_json(FIXTURE / "operators" / "core.json")["operators"],
            canonical_bindings=environment["canonical_bindings"],
            local_declarations=environment["local_declarations"],
            candidate_assertion_ids=environment["candidate_assertion_ids"],
            canonical_assertion_ids=environment["canonical_assertion_ids"],
            jcs_serializer=jcs_text,
        )

    def test_leaf_round_trips(self) -> None:
        for case in self.vectors["leaf_cases"]:
            with self.subTest(case=case["name"]):
                parsed = self.reference.parse_leaf(
                    case["canonical_text"], self.snapshot_ref
                )
                self.assertEqual(parsed, case["authoritative_json"])
                self.assertEqual(
                    self.reference.render_leaf(
                        case["authoritative_json"], self.snapshot_ref
                    ),
                    case["canonical_text"],
                )

    def test_equation_round_trips(self) -> None:
        for case in self.examples["canonical_text_examples"]:
            with self.subTest(case=case["name"]):
                parsed = self.reference.parse_equation(
                    case["canonical_text"], self.snapshot_ref
                )
                self.assertEqual(parsed, case["authoritative_json"])
                self.assertEqual(
                    self.reference.render_equation(
                        case["authoritative_json"], self.snapshot_ref
                    ),
                    case["canonical_text"],
                )

    def test_invalid_leaf_text_fails_closed(self) -> None:
        for case in self.vectors["leaf_error_cases"]:
            with self.subTest(case=case["name"]):
                with self.assertRaisesRegex(
                    CanonicalTextError, case["expected_error_contains"]
                ):
                    self.reference.parse_leaf(case["canonical_text"], self.snapshot_ref)

    def test_invalid_equation_text_fails_closed(self) -> None:
        for case in self.vectors["equation_error_cases"]:
            with self.subTest(case=case["name"]):
                with self.assertRaisesRegex(
                    CanonicalTextError, case["expected_error_contains"]
                ):
                    self.reference.parse_equation(
                        case["canonical_text"], self.snapshot_ref
                    )

    def test_snapshot_reference_mismatch_fails_closed(self) -> None:
        for case in self.vectors["snapshot_ref_error_cases"]:
            with self.subTest(case=case["name"]):
                with self.assertRaisesRegex(
                    CanonicalTextError, case["expected_error_contains"]
                ):
                    self.reference.parse_equation(
                        case["canonical_text"], case["snapshot_ref_override"]
                    )

    def test_duplicate_assertion_environment_ids_fail_closed(self) -> None:
        environment = self.vectors["environment"]
        with self.assertRaisesRegex(
            CanonicalTextError, "duplicate candidate assertion ID"
        ):
            ReferenceEnvironment(
                snapshot_ref=self.snapshot_ref,
                concepts=read_json(FIXTURE / "concepts" / "core.json")["concepts"],
                operators=read_json(FIXTURE / "operators" / "core.json")["operators"],
                canonical_bindings=environment["canonical_bindings"],
                local_declarations=environment["local_declarations"],
                candidate_assertion_ids=["created-by-1", "created-by-1"],
                canonical_assertion_ids=environment["canonical_assertion_ids"],
                jcs_serializer=jcs_text,
            )


if __name__ == "__main__":
    unittest.main()
