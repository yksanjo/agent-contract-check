import unittest

from contract_check import check_contract, summarize, main


def producer():
    """Synthetic research-agent output schema."""
    return {
        "x-version": "1.2",
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "score": {"type": "integer"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": ["draft", "final"]},
            "finished_at": {"type": "string", "format": "date-time"},
            "extra_debug": {"type": "string"},
        },
        "required": ["title", "score", "status"],
    }


def consumer():
    """Synthetic writer-agent input schema."""
    return {
        "x-version": "1.2",
        "type": "object",
        "properties": {
            "title": {"type": "string"},
            "score": {"type": "number"},
            "tags": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "string", "enum": ["draft", "final"]},
            "finished_at": {"type": "string", "format": "date-time"},
        },
        "required": ["title", "score", "status"],
    }


def rules(findings):
    return [f["rule"] for f in findings]


def errors(findings):
    return [f for f in findings if f["severity"] == "error"]


class TestCompatiblePair(unittest.TestCase):
    def test_compatible_pair_passes(self):
        findings = check_contract(producer(), consumer())
        self.assertEqual(errors(findings), [], findings)

    def test_integer_feeds_number(self):
        findings = check_contract(producer(), consumer())
        self.assertNotIn("type-mismatch", rules(findings))

    def test_summary_ok(self):
        self.assertTrue(summarize(check_contract(producer(), consumer()))["ok"])


class TestMissingFields(unittest.TestCase):
    def test_consumer_required_field_missing(self):
        p = producer(); del p["properties"]["score"]
        p["required"] = ["title", "status"]
        findings = check_contract(p, consumer())
        self.assertIn("missing-required-field", rules(findings))
        self.assertTrue(errors(findings))

    def test_consumer_optional_field_missing_is_fine(self):
        c = consumer(); c["properties"]["nickname"] = {"type": "string"}
        findings = check_contract(producer(), c)
        self.assertEqual(errors(findings), [], findings)


class TestTypeCompatibility(unittest.TestCase):
    def test_string_into_integer_rejected(self):
        p = producer(); p["properties"]["score"] = {"type": "string"}
        self.assertIn("type-mismatch", rules(check_contract(p, consumer())))

    def test_number_into_integer_rejected(self):
        p = producer(); p["properties"]["score"] = {"type": "number"}
        c = consumer(); c["properties"]["score"] = {"type": "integer"}
        self.assertIn("type-mismatch", rules(check_contract(p, c)))

    def test_unknown_type_is_invalid_schema(self):
        p = producer(); p["type"] = "blob"
        self.assertIn("invalid-schema", rules(check_contract(p, consumer())))

    def test_non_object_schema(self):
        self.assertIn("invalid-schema", rules(check_contract([1], consumer())))


class TestEnumAndFormat(unittest.TestCase):
    def test_producer_enum_wider_than_consumer(self):
        p = producer()
        p["properties"]["status"]["enum"] = ["draft", "final", "archived"]
        findings = check_contract(p, consumer())
        self.assertIn("enum-violation", rules(findings))
        self.assertTrue(errors(findings))

    def test_producer_enum_narrower_is_fine(self):
        p = producer(); p["properties"]["status"]["enum"] = ["final"]
        self.assertNotIn("enum-violation", rules(check_contract(p, consumer())))

    def test_format_mismatch_warns(self):
        c = consumer(); c["properties"]["finished_at"]["format"] = "date"
        findings = check_contract(producer(), c)
        self.assertIn("format-mismatch", rules(findings))
        self.assertEqual(errors(findings), [], findings)  # warning only


class TestObjectsArraysVersions(unittest.TestCase):
    def test_closed_consumer_with_extra_producer_fields(self):
        c = consumer(); c["additionalProperties"] = False
        findings = check_contract(producer(), c)
        self.assertIn("unexpected-field", rules(findings))
        self.assertEqual(errors(findings), [], findings)  # warning only

    def test_nested_object_recursion(self):
        p = producer(); c = consumer()
        p["properties"]["meta"] = {"type": "object",
                                   "properties": {"run_id": {"type": "string"}}}
        c["properties"]["meta"] = {"type": "object",
                                   "properties": {"run_id": {"type": "integer"}},
                                   "required": ["run_id"]}
        findings = check_contract(p, c)
        self.assertIn("type-mismatch", rules(findings))
        self.assertTrue(any("meta.run_id" in f["path"] for f in findings))

    def test_array_items_recursion(self):
        c = consumer()
        c["properties"]["tags"]["items"] = {"type": "integer"}
        findings = check_contract(producer(), c)
        self.assertIn("type-mismatch", rules(findings))
        self.assertTrue(any("tags[]" in f["path"] for f in findings))

    def test_consumer_items_unspecified_producer(self):
        p = producer(); p["properties"]["tags"] = {"type": "array"}
        findings = check_contract(p, consumer())
        self.assertIn("unspecified-items", rules(findings))

    def test_version_skew_warns(self):
        c = consumer(); c["x-version"] = "2.0"
        findings = check_contract(producer(), c)
        self.assertIn("version-skew", rules(findings))
        self.assertEqual(errors(findings), [], findings)

    def test_unsupported_constraint_warns_not_fails(self):
        p = producer(); p["properties"]["title"]["pattern"] = "^[A-Z]"
        findings = check_contract(p, consumer())
        self.assertIn("unsupported-constraint", rules(findings))
        self.assertEqual(errors(findings), [], findings)


class TestCLI(unittest.TestCase):
    def test_exit_codes(self):
        import json, os, tempfile
        with tempfile.TemporaryDirectory() as td:
            good_p = os.path.join(td, "p.json")
            good_c = os.path.join(td, "c.json")
            bad_p = os.path.join(td, "bad.json")
            with open(good_p, "w") as fh: json.dump(producer(), fh)
            with open(good_c, "w") as fh: json.dump(consumer(), fh)
            broken = producer(); del broken["properties"]["title"]
            with open(bad_p, "w") as fh: json.dump(broken, fh)
            self.assertEqual(main([good_p, good_c, "--json"]), 0)
            self.assertEqual(main([bad_p, good_c]), 1)
            self.assertEqual(main([os.path.join(td, "nope"), good_c]), 2)


if __name__ == "__main__":
    unittest.main()
