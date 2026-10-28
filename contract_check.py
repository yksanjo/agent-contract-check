#!/usr/bin/env python3
"""agent-contract-check: producer/consumer schema compatibility for agent pipelines.

When one agent's output feeds another agent's input, the pair only works if
the consumer's contract is satisfied by the producer's contract. This tool
compares two JSON Schema documents (a practical subset) and reports where
the producer can emit data the consumer cannot accept.

Direction matters: PRODUCER describes what the upstream agent may emit,
CONSUMER describes what the downstream agent requires. A consumer-required
field the producer never emits is an error; a producer type the consumer
cannot accept is an error; producer enum values outside the consumer's enum
are an error.

Offline, no executor, review signals only. Subset of JSON Schema - see
README.md for what is and is not checked.
"""
from __future__ import annotations

import argparse
import json
import sys

ERROR = "error"
WARN = "warning"
INFO = "info"

JSON_TYPES = {"object", "array", "string", "number", "integer", "boolean", "null"}
# consumer type -> producer types it can always accept
TYPE_ACCEPTS = {
    "number": {"number", "integer"},
    "integer": {"integer"},
    "string": {"string"},
    "boolean": {"boolean"},
    "object": {"object"},
    "array": {"array"},
    "null": {"null"},
}
SUPPORTED_KEYS = {
    "type", "properties", "required", "items", "enum", "format",
    "additionalProperties", "x-version", "title", "description",
}


def _finding(rule, severity, path, message):
    return {"rule": rule, "severity": severity, "path": path, "message": message}


def _unsupported(schema, path, findings):
    for key in ("$ref", "anyOf", "oneOf", "allOf", "not", "pattern",
                "minimum", "maximum", "minLength", "maxLength"):
        if isinstance(schema, dict) and key in schema:
            findings.append(_finding(
                "unsupported-constraint", WARN, path,
                f'"{key}" is not evaluated by this subset checker; '
                "compatibility there is unverified"))


def _types_of(schema):
    t = schema.get("type")
    if isinstance(t, str):
        return {t}
    if isinstance(t, list):
        return {x for x in t if isinstance(x, str)}
    return set()


def _compare(producer, consumer, path, findings):
    if not isinstance(producer, dict) or not isinstance(consumer, dict):
        findings.append(_finding(
            "invalid-schema", ERROR, path, "schema nodes must be objects"))
        return

    _unsupported(producer, path + " (producer)", findings)
    _unsupported(consumer, path + " (consumer)", findings)

    # --- types ---------------------------------------------------------
    p_types = _types_of(producer)
    c_types = _types_of(consumer)
    if p_types and c_types:
        accepted = set()
        for ct in c_types:
            accepted |= TYPE_ACCEPTS.get(ct, set())
        for pt in sorted(p_types):
            if pt not in accepted:
                findings.append(_finding(
                    "type-mismatch", ERROR, path,
                    f'producer may emit "{pt}" which the consumer '
                    f"({sorted(c_types)}) cannot accept"))

    # --- enums -----------------------------------------------------------
    p_enum = producer.get("enum")
    c_enum = consumer.get("enum")
    if isinstance(p_enum, list) and isinstance(c_enum, list):
        extra = [v for v in p_enum if v not in c_enum]
        if extra:
            findings.append(_finding(
                "enum-violation", ERROR, path,
                f"producer may emit {extra!r} outside the consumer's enum "
                f"{c_enum!r}"))

    # --- formats ---------------------------------------------------------
    p_fmt, c_fmt = producer.get("format"), consumer.get("format")
    if p_fmt and c_fmt and p_fmt != c_fmt:
        findings.append(_finding(
            "format-mismatch", WARN, path,
            f'producer format "{p_fmt}" vs consumer format "{c_fmt}"'))

    # --- objects -----------------------------------------------------------
    p_props = producer.get("properties") or {}
    c_props = consumer.get("properties") or {}
    c_required = consumer.get("required") or []
    for field in c_required:
        if field not in p_props:
            findings.append(_finding(
                "missing-required-field", ERROR, f"{path}.{field}",
                f'consumer requires "{field}" but the producer never emits it'))
    for field, c_sub in c_props.items():
        if field in p_props:
            _compare(p_props[field], c_sub, f"{path}.{field}", findings)
        elif field in c_required:
            pass  # already reported above
    if consumer.get("additionalProperties") is False and p_props:
        extras = sorted(set(p_props) - set(c_props))
        if extras:
            findings.append(_finding(
                "unexpected-field", WARN, path,
                f"consumer is closed (additionalProperties false) but producer "
                f"also emits {extras}; consumer may reject whole payloads"))

    # --- arrays ------------------------------------------------------------
    if "array" in p_types and "array" in c_types:
        p_items = producer.get("items")
        c_items = consumer.get("items")
        if isinstance(p_items, dict) and isinstance(c_items, dict):
            _compare(p_items, c_items, path + "[]", findings)
        elif isinstance(c_items, dict) and not isinstance(p_items, dict):
            findings.append(_finding(
                "unspecified-items", WARN, path,
                "consumer constrains array items but the producer leaves "
                "items unspecified"))


def check_contract(producer: dict, consumer: dict) -> list:
    """Compare a producer schema with a consumer schema."""
    findings: list[dict] = []
    if not isinstance(producer, dict) or not isinstance(consumer, dict):
        return [_finding("invalid-schema", ERROR, "$",
                         "both schemas must be JSON objects")]

    p_ver, c_ver = producer.get("x-version"), consumer.get("x-version")
    if p_ver is not None and c_ver is not None and p_ver != c_ver:
        findings.append(_finding(
            "version-skew", WARN, "$",
            f'producer x-version "{p_ver}" vs consumer "{c_ver}"'))

    for side, schema in (("producer", producer), ("consumer", consumer)):
        t = _types_of(schema)
        bad = t - JSON_TYPES
        if bad:
            findings.append(_finding(
                "invalid-schema", ERROR, f"$ ({side})",
                f"unknown JSON type(s) {sorted(bad)}"))

    _compare(producer, consumer, "$", findings)

    order = {ERROR: 0, WARN: 1, INFO: 2}
    findings.sort(key=lambda f: (order[f["severity"]], f["rule"], f["path"]))
    return findings


def summarize(findings: list) -> dict:
    out = {"errors": 0, "warnings": 0, "infos": 0}
    for f in findings:
        out[{ERROR: "errors", WARN: "warnings", INFO: "infos"}[f["severity"]]] += 1
    out["ok"] = out["errors"] == 0
    return out


def render_text(findings: list, summary: dict) -> str:
    lines = [f"agent-contract-check: {summary['errors']} error(s), "
             f"{summary['warnings']} warning(s), {summary['infos']} info"]
    for f in findings:
        lines.append(f"[{f['severity']}] {f['rule']} at {f['path']}: {f['message']}")
    if not findings:
        lines.append("no findings: producer output satisfies the consumer contract")
    return "\n".join(lines)


def main(argv: list | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check producer/consumer JSON Schema compatibility.")
    parser.add_argument("producer", help="producer schema JSON file, or - for stdin")
    parser.add_argument("consumer", help="consumer schema JSON file")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    try:
        raw_p = sys.stdin.read() if args.producer == "-" \
            else open(args.producer, encoding="utf-8").read()
        producer = json.loads(raw_p)
        consumer = json.loads(open(args.consumer, encoding="utf-8").read())
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    findings = check_contract(producer, consumer)
    summary = summarize(findings)
    if args.json:
        print(json.dumps({"ok": summary["ok"], "summary": summary,
                          "findings": findings}, indent=2))
    else:
        print(render_text(findings, summary))
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
