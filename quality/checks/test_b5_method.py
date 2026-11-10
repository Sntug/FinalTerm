import json
import unittest

from src.collect.common import REPO_ROOT
from src.nlp.rules import Extractor

A_DICTIONARY = json.loads((REPO_ROOT / "config/a4_dictionary.json").read_text(encoding="utf-8"))
METHODS = json.loads((REPO_ROOT / "config/b5_method_dictionary.json").read_text(encoding="utf-8"))


def accepted(extractor, case):
    return sorted({c.entity_id for c in extractor.candidates(case["text"], case["field"]) if c.rule_id})


class MethodRulesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.merged = Extractor({**A_DICTIONARY, "methods": METHODS["methods"]}, "blank")
        cls.base = Extractor(A_DICTIONARY, "blank")

    def test_method_cases(self):
        cases = json.loads((REPO_ROOT / "quality/fixtures/b5_method_cases.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(sum(bool(c["expected"]) for c in cases), 10)
        self.assertGreaterEqual(sum(not c["expected"] for c in cases), 10)
        for case in cases:
            with self.subTest(text=case["text"]):
                self.assertEqual(accepted(self.merged, case), sorted(case["expected"]))

    def test_a4_cases_unchanged_with_methods(self):
        for name in ("a4_dev.json", "a4_eval.json"):
            for case in json.loads((REPO_ROOT / "quality/fixtures" / name).read_text(encoding="utf-8")):
                with self.subTest(text=case["text"]):
                    self.assertEqual(accepted(self.merged, case), accepted(self.base, case))
                    self.assertEqual(accepted(self.merged, case), sorted(case["expected"]))

    def test_no_methods_without_dictionary(self):
        self.assertFalse(list(self.base.candidates("We use a vision transformer.", "abstract")))

    def test_no_alias_collision(self):
        seen = {}
        for group in ("tasks", "datasets", "methods"):
            for item in (A_DICTIONARY | METHODS)[group]:
                for alias in item["aliases"]:
                    self.assertEqual(seen.setdefault(alias.lower(), item["id"]), item["id"])


if __name__ == "__main__":
    unittest.main()
