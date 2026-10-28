# agent-contract-check

Check that a producer agent's output schema still satisfies the consumer
agent's input schema before the pipeline runs.

Multi-agent pipelines break quietly: the research agent drops a field, turns
an integer into a string, or adds a status value the writer agent has never
heard of - and the failure shows up downstream as a confusing crash or,
worse, silent bad data. `agent-contract-check` compares the two contracts
offline and reports every incompatibility it can prove.

Direction matters. The **producer** schema describes what the upstream agent
may emit; the **consumer** schema describes what the downstream agent
requires. The check asks one question: can the producer emit something the
consumer cannot accept, or omit something the consumer requires?

Exit codes: `0` compatible, `1` any error, `2` usage/input problems.

## Requirements

Python 3.10+. Standard library only - no dependencies, no network.

## Usage

```
python3 contract_check.py producer.schema.json consumer.schema.json
python3 contract_check.py producer.schema.json consumer.schema.json --json
```

Run the demo and tests:

```
python3 demo.py
python3 -m unittest test_contract_check
```

## Rules

| rule | severity | what it catches |
|------|----------|-----------------|
| `invalid-schema` | error | malformed schema input, unknown JSON types |
| `missing-required-field` | error | consumer requires a field the producer never emits |
| `type-mismatch` | error | producer type the consumer cannot accept (`integer` feeds `number`, not vice versa) |
| `enum-violation` | error | producer enum values outside the consumer's enum |
| `format-mismatch` | warning | e.g. producer `date-time` vs consumer `date` |
| `unexpected-field` | warning | consumer is closed (`additionalProperties: false`) but producer emits extra fields |
| `unspecified-items` | warning | consumer constrains array items the producer leaves untyped |
| `version-skew` | warning | differing `x-version` markers |
| `unsupported-constraint` | warning | `$ref`, `anyOf`/`oneOf`/`allOf`, `pattern`, numeric bounds - not evaluated, compatibility unverified |

Schemas recurse through `properties` and `items`, so nested objects and
array element types are checked too.

## Limits

- **Subset of JSON Schema.** `$ref` is not resolved; `anyOf`/`oneOf`/
  `allOf`/`not`, `pattern`, and numeric bounds are reported as unverified
  rather than checked. A pass does not cover them.
- **Static contract comparison only.** It does not validate real payloads
  against either schema, and it does not prove the producer actually honors
  its own schema at runtime - pair it with live payload validation for that.
- **Direction is caller-supplied.** Swapping the two files inverts the
  answer; the tool cannot tell which agent is upstream.
- A clean result means "no incompatibility found within the checked
  subset" - not that the pipeline is correct, safe, or authorized.
- All demo and test data is synthetic.

## License

MIT - see [LICENSE](LICENSE).
