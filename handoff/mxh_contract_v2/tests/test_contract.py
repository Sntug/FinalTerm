import copy
import json
import tempfile
import unittest
from pathlib import Path

from contract_v2.model import AUTHORSHIPS, FILES, REGISTRY, RELATIONS, schema_for
from contract_v2.text import canonical_json, evidence_id, normalize, sha256, text_record, validate_nlp_evidence
from contract_v2.verify import load_records, verify
from contract_v2.migrate import migrate

ROOT = Path(__file__).resolve().parents[1]


class ContractTests(unittest.TestCase):
    def sample(self):
        text = text_record("p","source","html:div#abstract.text","  We  evaluate on COCO. ","parser-1","2026-11-06T00:00:00Z")
        e = dict(evidence_kind="nlp", paper_id="p",source_record_id="source",field_path=text["field_path"],
                 text_version_id=text["text_version_id"],normalized_text_sha256=text["normalized_text_sha256"],
                 normalization_version=text["normalization_version"],start_char=15,end_char=19,evidence_text="COCO",
                 rule_id="eval",rule_version="1",supporting_evidence_ids=[])
        return text,e

    def test_registry_15_columns_remain(self):
        self.assertEqual(len(REGISTRY),15)
        self.assertEqual(REGISTRY[:7],"paper_id doi cvf_url conference conference_year owner status".split())

    def test_10_relations_not_11(self):
        self.assertEqual(len({r[0] for r in RELATIONS}),10)

    def test_identity_and_affiliation_provenance_are_separate(self):
        self.assertIn("identity_source_record_id",AUTHORSHIPS)
        self.assertIn("affiliation_source_record_id",AUTHORSHIPS)

    def test_unicode_and_whitespace_are_deterministic(self):
        self.assertEqual(normalize("  e\u0301 \n COCO "),"é COCO")

    def test_hash_is_of_entire_field(self):
        text,e = self.sample()
        self.assertEqual(text["normalized_text_sha256"],sha256(b"We evaluate on COCO."))
        self.assertNotEqual(text["normalized_text_sha256"],sha256(b"COCO"))

    def test_exact_half_open_slice_is_accepted(self):
        text,e = self.sample(); validate_nlp_evidence(e,text)

    def test_stale_offsets_are_rejected(self):
        text,e = self.sample(); e["start_char"]-=1
        with self.assertRaises(ValueError): validate_nlp_evidence(e,text)

    def test_wrong_source_hash_is_rejected(self):
        text,e = self.sample(); e["normalized_text_sha256"]="wrong"
        with self.assertRaises(ValueError): validate_nlp_evidence(e,text)

    def test_normalizer_version_is_bound(self):
        text,e = self.sample(); e["normalization_version"]="other"
        with self.assertRaises(ValueError): validate_nlp_evidence(e,text)

    def test_changed_parser_creates_new_text_version(self):
        text,e = self.sample()
        other=text_record("p","source",text["field_path"],text["normalized_text"],"parser-2",text["captured_at"])
        self.assertNotEqual(text["text_version_id"],other["text_version_id"])

    def test_evidence_id_changes_with_text_version(self):
        text,e=self.sample(); changed=copy.deepcopy(e); changed["text_version_id"]="new"
        self.assertNotEqual(evidence_id(e),evidence_id(changed))

    def test_mandatory_key_cannot_be_omitted(self):
        schema=schema_for("evidence.jsonl")
        self.assertIn("normalized_text_sha256",schema["required"])
        self.assertFalse(schema["additionalProperties"])

    def test_snapshot_tag_is_not_self_referential_csv_column(self):
        self.assertNotIn("snapshot_id",FILES["nodes.csv"][0])
        self.assertNotIn("snapshot_id",FILES["edges.csv"][0])

    def test_migration_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): migrate(Path(d)/"input",Path(d))

    def test_delivered_metadata_snapshot_checks(self):
        result=verify(ROOT/"pilot_v2")
        self.assertTrue(result["passed"])
        self.assertFalse(result["graph_ready"])
        self.assertEqual(result["text_versions_checked"],120)


if __name__=="__main__": unittest.main()
