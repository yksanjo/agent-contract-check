#!/usr/bin/env python3
"""Demo: check one compatible and one drifted producer/consumer pair.

Synthetic schemas for a research-agent feeding a writer-agent.
"""
import copy

from contract_check import check_contract, summarize, render_text

PRODUCER = {
    "x-version": "1.2",
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "score": {"type": "integer"},
        "tags": {"type": "array", "items": {"type": "string"}},
        "status": {"type": "string", "enum": ["draft", "final"]},
        "finished_at": {"type": "string", "format": "date-time"},
    },
    "required": ["title", "score", "status"],
}

CONSUMER = {
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


def run(title, producer, consumer):
    findings = check_contract(producer, consumer)
    print(f"=== {title} ===")
    print(render_text(findings, summarize(findings)))
    print()


if __name__ == "__main__":
    run("compatible pair", PRODUCER, CONSUMER)

    drifted = copy.deepcopy(PRODUCER)
    drifted["x-version"] = "1.3"
    del drifted["properties"]["title"]            # producer dropped a field
    drifted["required"] = ["score", "status"]
    drifted["properties"]["score"] = {"type": "string"}   # int became string
    drifted["properties"]["status"]["enum"] = ["draft", "final", "archived"]
    run("drifted producer (consumer breaks)", drifted, CONSUMER)
