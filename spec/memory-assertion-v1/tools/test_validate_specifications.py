#!/usr/bin/env python3
"""Regression tests for the offline specification validation entrypoint."""

from __future__ import annotations

import json
import unittest
import warnings
from unittest.mock import patch

import tools.validate_specifications as validation

from tools.validate_specifications import (
    FIXTURE,
    _fixture_documents,
    canonical_sha256,
    canonicalize,
    read_json,
    request_hash_preimage,
    request_sha256,
    validate_jcs_domain,
    validate_identity_seed_registry,
    validate_jcs_vectors,
    validate_json_inventory,
    validate_markdown_links,
    validate_reference_manifests,
    validate_required_migration_files,
    validate_schemas,
    validate_snapshot_vectors,
    reject_duplicate_object_pairs,
)


class SpecificationValidationTests(unittest.TestCase):
    def test_registered_concept_parents_order_is_canonicalized(self) -> None:
        first = {
            "concepts": [
                {
                    "id": "concept_aaaaaaaaaaaa",
                    "canonical_name": "Example",
                    "parents": [
                        "concept_cccccccccccc",
                        "concept_bbbbbbbbbbbb",
                    ],
                }
            ]
        }
        second = {
            "concepts": [
                {
                    "id": "concept_aaaaaaaaaaaa",
                    "canonical_name": "Example",
                    "parents": [
                        "concept_bbbbbbbbbbbb",
                        "concept_cccccccccccc",
                    ],
                }
            ]
        }
        self.assertEqual(canonicalize(first), canonicalize(second))
        self.assertEqual(canonical_sha256(first), canonical_sha256(second))

    def test_unregistered_supply_namespace_array_order_is_preserved(self) -> None:
        first = {
            "concepts": [
                {
                    "id": "concept_aaaaaaaaaaaa",
                    "canonical_name": "Example",
                    "supply": {
                        "other_profile": {
                            "parents": ["second", "first"]
                        }
                    },
                }
            ]
        }
        second = {
            "concepts": [
                {
                    "id": "concept_aaaaaaaaaaaa",
                    "canonical_name": "Example",
                    "supply": {
                        "other_profile": {
                            "parents": ["first", "second"]
                        }
                    },
                }
            ]
        }
        self.assertNotEqual(canonicalize(first), canonicalize(second))
        self.assertNotEqual(canonical_sha256(first), canonical_sha256(second))

    def test_required_input_indexes_are_sorted_numerically(self) -> None:
        document = {
            "operators": [
                {
                    "id": "operator_aaaaaaaaaaaa",
                    "canonical_name": "example",
                    "supply": {
                        "memory_assertion": {
                            "definedness_contract": {
                                "required_input_indexes": [2, 10, 1]
                            }
                        }
                    },
                }
            ]
        }
        canonical = canonicalize(document)
        indexes = canonical["operators"][0]["supply"]["memory_assertion"][
            "definedness_contract"
        ]["required_input_indexes"]
        self.assertEqual(indexes, [1, 2, 10])

    def test_external_mapping_provenance_refs_are_canonicalized(self) -> None:
        for owner_key, owner_id, canonical_name in (
            ("concepts", "concept_aaaaaaaaaaaa", "Example"),
            ("operators", "operator_aaaaaaaaaaaa", "example"),
        ):
            with self.subTest(owner_key=owner_key):
                first = {
                    owner_key: [
                        {
                            "id": owner_id,
                            "canonical_name": canonical_name,
                            "supply": {
                                "memory_assertion": {
                                    "external_mappings": [
                                        {
                                            "source": "example",
                                            "external_id": "external-1",
                                            "relation": "exact",
                                            "provenance_refs": ["second", "first"],
                                        }
                                    ]
                                }
                            },
                        }
                    ]
                }
                second = json.loads(json.dumps(first))
                second[owner_key][0]["supply"]["memory_assertion"][
                    "external_mappings"
                ][0]["provenance_refs"] = ["first", "second"]
                self.assertEqual(canonicalize(first), canonicalize(second))
                self.assertEqual(canonical_sha256(first), canonical_sha256(second))

    def test_path_wildcard_does_not_match_an_object_property(self) -> None:
        document = {"concepts": {"0": {"parents": ["second", "first"]}}}
        self.assertEqual(
            canonicalize(document)["concepts"]["0"]["parents"],
            ["second", "first"],
        )

    def test_registered_string_set_uses_nfc_utf8_byte_order(self) -> None:
        document = {
            "concepts": [
                {
                    "id": "concept_aaaaaaaaaaaa",
                    "canonical_name": "Example",
                    "parents": ["0", "\u001f"],
                }
            ]
        }
        self.assertEqual(canonicalize(document)["concepts"][0]["parents"], ["\u001f", "0"])

    def test_all_three_schemas_are_counted(self) -> None:
        self.assertEqual(validate_schemas(), 3)

    def test_jcs_vectors_are_consumed(self) -> None:
        self.assertEqual(validate_jcs_vectors(), (2, 1))

    def test_snapshot_vectors_are_consumed(self) -> None:
        self.assertEqual(validate_snapshot_vectors(), 8)

    def test_every_json_file_is_parsed_strictly(self) -> None:
        self.assertGreaterEqual(validate_json_inventory(), 13)

    def test_duplicate_json_object_keys_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            json.loads(
                '{"a":1,"a":2}',
                object_pairs_hook=reject_duplicate_object_pairs,
            )

    def test_jcs_domain_rejects_unsafe_integer_and_unpaired_surrogate(self) -> None:
        with self.assertRaisesRegex(ValueError, "safe-integer range"):
            validate_jcs_domain({"value": 9_007_199_254_740_992})
        with self.assertRaisesRegex(ValueError, "unpaired Unicode surrogate"):
            validate_jcs_domain({"value": "\ud800"})

    def test_request_hash_replaces_raw_credential_reference_with_fingerprint(self) -> None:
        request = {
            "document_kind": "nl2ke_request",
            "execution": {
                "credential": {
                    "mode": "caller_managed",
                    "credential_ref": "secret://tenant/one",
                    "credential_ref_fingerprint": "a" * 64,
                }
            },
        }
        preimage = request_hash_preimage(request)
        self.assertNotIn("credential_ref", preimage["execution"]["credential"])
        changed_reference = json.loads(json.dumps(request))
        changed_reference["execution"]["credential"]["credential_ref"] = (
            "secret://tenant/two"
        )
        self.assertEqual(request_sha256(request), request_sha256(changed_reference))
        changed_fingerprint = json.loads(json.dumps(request))
        changed_fingerprint["execution"]["credential"][
            "credential_ref_fingerprint"
        ] = "b" * 64
        self.assertNotEqual(request_sha256(request), request_sha256(changed_fingerprint))

    def test_reference_manifests_bind_size_and_hash(self) -> None:
        self.assertEqual(validate_reference_manifests(), (4, 2))

    def test_identity_seed_registry_reproduces_every_fixture_id(self) -> None:
        manifest = read_json(FIXTURE / "snapshot.manifest.json")
        self.assertEqual(
            validate_identity_seed_registry(_fixture_documents(manifest)), 18
        )

    def test_local_markdown_links_resolve(self) -> None:
        self.assertGreaterEqual(validate_markdown_links(), 8)

    def test_migration_required_files_exist(self) -> None:
        self.assertGreaterEqual(validate_required_migration_files(), 19)

    def test_duplicate_valid_request_fixture_ids_are_rejected(self) -> None:
        examples_path = validation.SCHEMA_DIR / "examples.json"
        examples = validation.read_json(examples_path)
        duplicate = json.loads(json.dumps(examples["cases"][0]))
        duplicate["name"] = "duplicate valid request id"
        examples["cases"].append(duplicate)
        original_read_json = validation.read_json

        def read_json_with_duplicate(path):
            if path == examples_path:
                return examples
            return original_read_json(path)

        with patch.object(
            validation, "read_json", side_effect=read_json_with_duplicate
        ):
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", DeprecationWarning)
                with self.assertRaisesRegex(
                    ValueError, "duplicate valid request_id fixture: 'request-1'"
                ):
                    validation.validate_exchange()


if __name__ == "__main__":
    unittest.main()
