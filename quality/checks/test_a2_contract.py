"""v2 contract/text checks ported without importing the handoff package."""
import copy
import unittest

from src.collect.common import REPO_ROOT
from src.collect.contract import CONTRACT_DIR, contract, schema_for, validate_json
from src.clean.text import evidence_id, normalize, sha256, text_record, validate_nlp_evidence


class ContractTests(unittest.TestCase):
    def sample(self):
        text = text_record("p", "source", "html:div#abstract.text", "  We  evaluate on COCO. ", "parser-1", "2026-11-06T00:00:00Z")
        evidence = {"evidence_kind": "nlp", "paper_id": "p", "source_record_id": "source", "field_path": text["field_path"],
                    "text_version_id": text["text_version_id"], "normalized_text_sha256": text["normalized_text_sha256"],
                    "normalization_version": text["normalization_version"], "start_char": 15, "end_char": 19,
                    "evidence_text": "COCO", "rule_id": "eval", "rule_version": "1", "supporting_evidence_ids": []}
        return text, evidence

    def test_canonical_schemas_are_byte_identical_to_handoff(self):
        original = REPO_ROOT / "handoff/mxh_contract_v2/schemas"
        self.assertEqual({p.name for p in original.glob("*.json")}, {p.name for p in CONTRACT_DIR.glob("*.json")})
        for path in original.glob("*.json"):
            with self.subTest(file=path.name):
                self.assertEqual(path.read_bytes(), (CONTRACT_DIR / path.name).read_bytes())

    def test_registry_labels_relations_and_separate_provenance(self):
        spec = contract()
        self.assertEqual(len(spec["files"]["paper_registry.csv"]["fields"]), 15)
        self.assertEqual(len(spec["node_labels"]), 8)
        self.assertEqual(len(spec["relations"]), 10)
        self.assertIn("identity_source_record_id", spec["files"]["authorships.csv"]["fields"])
        self.assertIn("affiliation_source_record_id", spec["files"]["authorships.csv"]["fields"])

    def test_missing_keys_wrong_type_and_minimum_are_rejected(self):
        schema = {"type": "object", "required": ["n"], "additionalProperties": False,
                  "properties": {"n": {"type": "integer", "minimum": 1}}}
        for value in ({}, {"n": True}, {"n": 0}, {"n": 2, "extra": 1}):
            self.assertTrue(validate_json(value, schema))
        self.assertEqual(validate_json({"n": 2}, schema), [])
        self.assertIn("normalized_text_sha256", schema_for("evidence.jsonl")["required"])

    def test_unicode_normalization_and_whole_field_hash(self):
        self.assertEqual(normalize("  e\u0301 \n COCO "), "é COCO")
        text, _ = self.sample()
        self.assertEqual(text["normalized_text_sha256"], sha256(b"We evaluate on COCO."))
        self.assertNotEqual(text["normalized_text_sha256"], sha256(b"COCO"))

    def test_half_open_binding_accepts_exact_slice_rejects_stale_fields(self):
        text, evidence = self.sample()
        validate_nlp_evidence(evidence, text)
        for field, value in (("start_char", 14), ("normalized_text_sha256", "wrong"), ("normalization_version", "other")):
            changed = {**evidence, field: value}
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate_nlp_evidence(changed, text)

    def test_parser_and_text_version_change_evidence_identity(self):
        text, evidence = self.sample()
        other = text_record("p", "source", text["field_path"], text["normalized_text"], "parser-2", text["captured_at"])
        self.assertNotEqual(text["text_version_id"], other["text_version_id"])
        changed = copy.deepcopy(evidence)
        changed["text_version_id"] = other["text_version_id"]
        self.assertNotEqual(evidence_id(evidence), evidence_id(changed))


if __name__ == "__main__":
    unittest.main()
