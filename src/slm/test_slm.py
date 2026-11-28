import hashlib
import json
import tempfile
import threading
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from src.slm import client, pilot

DIGEST = "a" * 64
SCHEMA = {"type": "object", "properties": {"tasks": {"type": "array", "items": {"type": "string"}, "maxItems": 2}},
          "required": ["tasks"], "additionalProperties": False}


class FakeOllama(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def send(self, body, status=200):
        raw = json.dumps(body).encode()
        self.send_response(status)
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        self.send({"models": [{"name": "fake:1b", "digest": self.server.digest}]})

    def do_POST(self):
        self.server.requests.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        if self.server.failures:
            status = self.server.failures.pop(0)
            return self.send({"error": "boom"}, status)
        self.send({"response": self.server.reply, "done_reason": self.server.done_reason,
                   "eval_count": 10, "eval_duration": 2_000_000_000, "total_duration": 3_000_000_000,
                   "load_duration": 500_000_000, "prompt_eval_count": 7})


class ClientTest(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeOllama)
        self.server.requests, self.server.reply = [], '{"tasks": ["segmentation"]}'
        self.server.digest, self.server.done_reason = DIGEST, "stop"
        self.server.failures = []
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.config = {"host": f"http://127.0.0.1:{self.server.server_address[1]}", "model": "fake:1b",
                       "model_digests": {"fake:1b": DIGEST}, "timeout_seconds": 5, "seed": 7, "temperature": 0,
                       "num_ctx": 2048, "num_predict": 64, "cache_dir": directory.name,
                       "retries": 2, "retry_wait_seconds": 0}

    def call(self, prompt="P", schema=SCHEMA, text="T"):
        return client.generate_json(prompt, schema, text, config=self.config)

    def test_sends_fixed_parameters_and_returns_dict(self):
        self.assertEqual(self.call(), {"tasks": ["segmentation"]})
        sent = self.server.requests[0]
        self.assertEqual((sent["model"], sent["think"], sent["stream"], sent["format"]), ("fake:1b", False, False, SCHEMA))
        self.assertEqual((sent["options"]["temperature"], sent["options"]["seed"]), (0, 7))

    def test_cache_name_content_and_offline_replay(self):
        self.call(prompt="SECRET PROMPT")
        expected = hashlib.sha256(json.dumps(["T", "SECRET PROMPT", DIGEST], ensure_ascii=False).encode()).hexdigest()
        path = Path(self.config["cache_dir"]) / f"{expected}.json"
        self.assertNotIn("SECRET PROMPT", path.read_text("utf-8"))
        self.config["host"] = "http://127.0.0.1:1"
        self.assertEqual(self.call(prompt="SECRET PROMPT"), {"tasks": ["segmentation"]})
        self.assertEqual(len(self.server.requests), 1)

    def test_changed_schema_or_text_calls_again(self):
        self.call()
        self.call(text="U")
        self.call(schema={"type": "object"})
        self.assertEqual(len(self.server.requests), 3)

    def test_invalid_output_raises_and_is_not_requested_twice(self):
        self.server.reply = '{"tasks": ["a", "b", "c"]}'
        for _ in range(2):
            with self.assertRaises(ValueError):
                self.call()
        self.assertEqual(len(self.server.requests), 1)

    def test_digest_mismatch_refuses_to_generate(self):
        self.server.digest = "b" * 64
        with self.assertRaises(RuntimeError):
            self.call()
        self.assertEqual(self.server.requests, [])

    def test_text_and_truncation(self):
        self.server.reply = "xin chào"
        self.assertEqual(client.generate_text("P", "T", config=self.config), "xin chào")
        self.assertNotIn("format", self.server.requests[0])
        self.server.done_reason = "length"
        with self.assertRaises(ValueError):
            client.generate_text("P", "other", config=self.config)

    def test_oversized_prompt_is_an_error_not_silently_cut(self):
        self.server.failures = [400]
        with self.assertRaisesRegex(RuntimeError, "boom"):
            self.call()
        sent = self.server.requests[0]
        self.assertEqual((sent["truncate"], sent["shift"], len(self.server.requests)), (False, False, 1))
        self.assertEqual(list(Path(self.config["cache_dir"]).iterdir()), [])

    def test_server_errors_are_retried_a_finite_number_of_times(self):
        self.server.failures = [500, 503]
        self.assertEqual(self.call(), {"tasks": ["segmentation"]})
        self.assertEqual(len(self.server.requests), 3)
        self.server.failures = [500] * 5
        with self.assertRaises(RuntimeError):
            self.call(text="U")
        self.assertEqual(len(self.server.requests), 6)

    def test_ollama_down_raises_and_caches_nothing(self):
        self.config["host"] = "http://127.0.0.1:1"
        with self.assertRaises(OSError):
            self.call()
        self.assertEqual(list(Path(self.config["cache_dir"]).iterdir()), [])

    def test_broken_json_raises_value_error(self):
        self.server.reply = '{"tasks": ["segm'
        with self.assertRaises(ValueError):
            self.call()

    def test_new_model_digest_does_not_reuse_the_old_cache(self):
        self.call()
        self.server.digest = "b" * 64
        self.config["model_digests"] = {"fake:1b": "b" * 64}
        self.call()
        self.assertEqual((len(self.server.requests), len(list(Path(self.config["cache_dir"]).iterdir()))), (2, 2))

    def test_unsupported_schema_is_rejected_before_calling_the_model(self):
        for schema in ({"type": ["string", "null"]}, {"type": "null"}, {"type": "array", "minItems": 1},
                       {"type": "object", "properties": {"a": {"anyOf": []}}}):
            with self.assertRaises(TypeError, msg=repr(schema)):
                self.call(schema=schema)
        self.assertEqual(self.server.requests, [])

    def test_schema_with_tuples_hits_the_cache(self):
        schema = {**SCHEMA, "required": ("tasks",)}
        self.call(schema=schema)
        self.call(schema=schema)
        self.assertEqual(len(self.server.requests), 1)

    def test_text_drops_reasoning_that_think_false_did_not_suppress(self):
        self.server.reply = "Hmm, let me see.\n</think>\n\nParis"
        self.assertEqual(client.generate_text("P", "T", config=self.config), "Paris")

    def test_failed_cache_write_leaves_no_partial_file(self):
        with mock.patch.object(client.os, "replace", side_effect=KeyboardInterrupt), self.assertRaises(KeyboardInterrupt):
            self.call()
        self.assertEqual(list(Path(self.config["cache_dir"]).iterdir()), [])


class ValidateTest(unittest.TestCase):
    def test_subset_of_json_schema(self):
        client.validate({"tasks": ["a"]}, SCHEMA)
        client.validate("x", {"type": "string", "enum": ["x"]})
        for value, schema in [({}, SCHEMA), ({"tasks": [1]}, SCHEMA), ({"tasks": [], "more": 1}, SCHEMA),
                              ([], SCHEMA), (True, {"type": "integer"}), ("y", {"enum": ["x"]})]:
            with self.assertRaises(ValueError, msg=repr(value)):
                client.validate(value, schema)


class PilotTest(unittest.TestCase):
    def setUp(self):
        self.pools = {"E1": [{"paper_id": f"p{i}", "title": "t", "abstract": "a"} for i in range(10)]
                            + [{"paper_id": "empty", "title": "t", "abstract": ""}]}

    def test_select_excludes_gold_and_empty_abstract_deterministically(self):
        gold = {"E1": {"p0", "p1"}}
        first = pilot.select(self.pools, gold, {"E1": 8}, "s")
        self.assertEqual(first, pilot.select(self.pools, gold, {"E1": 8}, "s"))
        self.assertEqual({p["paper_id"] for _, p in first}, {f"p{i}" for i in range(2, 10)})

    def test_select_fails_when_gold_ids_do_not_match_the_pool(self):
        with self.assertRaises(ValueError):
            pilot.select(self.pools, {"E1": {"other-id-format"}}, {"E1": 2}, "s")

    def test_summarize_measures_only_from_rows(self):
        row = {"model": "m", "valid": True, "eval_count": 100, "eval_seconds": 4.0, "seconds": 10.0,
               "load_seconds": 0.5, "ram_rss_gb": 5.0, "loaded_gb": 5.5}
        got = pilot.summarize([row, {**row, "valid": False, "seconds": 20.0, "ram_rss_gb": 6.0}], 1750)
        self.assertEqual((got["valid_json_rate"], got["tokens_per_second"], got["mean_seconds_per_paper"]),
                         (0.5, 25.0, 15.0))
        self.assertEqual((got["hours_for_1750_papers"], got["peak_ram_rss_gb"]), (7.29, 6.0))

    def test_decide_keeps_primary_only_if_fast_and_valid(self):
        fast, slow = {"hours_for_1750_papers": 3, "valid_json_rate": 1.0}, {"hours_for_1750_papers": 20, "valid_json_rate": 1.0}
        self.assertEqual(pilot.decide({"big": fast, "small": fast}, ["big", "small"], 8, 0.95), "big")
        self.assertEqual(pilot.decide({"big": slow, "small": fast}, ["big", "small"], 8, 0.95), "small")
        self.assertIsNone(pilot.decide({"big": slow, "small": {**fast, "valid_json_rate": 0.5}}, ["big", "small"], 8, 0.95))


if __name__ == "__main__":
    unittest.main()
