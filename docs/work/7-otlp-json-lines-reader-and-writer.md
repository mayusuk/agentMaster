# Work plan: OTLP JSON Lines reader and writer

**Issue:** [#7](https://github.com/mayusuk/agentMaster/issues/7) (feature)
**Branch:** `issue/7-otlp-json-lines-reader-and-writer`
**Base:** `origin/main @ 698a463` (checked before branching)
**Status:** In progress

## Summary

Adds `src/eagain/otlp/`, a hand-written reader and writer for the OTLP File format: JSON Lines with one traces export object (`{"resourceSpans": [...]}`) per line. The reader decodes every attribute value type, integer-as-string timestamps and hex IDs. It reports each bad line with its line number and a reason, then carries on with the next line, and it says when a line holds logs or metrics instead of traces. The writer produces the same bytes for the same spans. `eagain validate` (#8), the normaliser (#9) and the importer (M3) are built on top of it.

## Context

- Plan M1.4 (`specs/001-agent-log-tracer/plan.md` section 4). M1 plan task T5 (`docs/plans/2026-11-03-v0-1-m1-format.md`).
- Spec 001 section 5: the input contract is the OTLP File format with one `resourceSpans` object per line. Lines are not ordered, so spans are assembled later by `traceId` and `parentSpanId` (that happens in the normaliser, #9, not here).
- Plan section 1: OTLP JSON is hand-written with no runtime dependency, because only the JSON encoding of traces is needed. Plan section 2: `otlp/` holds read, write and validate. Rules never import `otlp`.
- FR-1 AC2 and AC4 (line numbers, reasons, rejecting logs and metrics) are tested at the CLI level by #8. This issue gives #8 the per-line errors and the signal kind it needs.
- The OTLP/JSON encoding rules come from the OTLP specification: lowerCamelCase keys, hex trace and span IDs, 64-bit integers as decimal strings, enums as integers, unknown fields ignored, and bytes as base64.
- NFR-1 (memory): the reader streams line by line instead of loading the whole file.

## Approach

- `otlp/data.py`: frozen dataclasses that mirror the OTLP trace messages. `TracesData` (one line) holds `ResourceSpans`, which hold a `Resource` and `ScopeSpans`, which hold an `InstrumentationScope` and `Span`s. A `Span` has `Event`s, `Link`s and a `Status`. Attributes are an ordered tuple of `KeyValue(key, value)`. Attribute values are native Python values: `str`, `bool`, `int`, `float`, `bytes`, `tuple` (array), `KvList` (kvlist), or `None` (empty `AnyValue`). Tuples keep the order and keep duplicate keys, so a read followed by a write never changes them.
- `otlp/writer.py`: `encode_line(TracesData) -> str` builds dicts in a fixed key order and dumps them compactly, with UTF-8 left as is. `write_lines(Iterable[TracesData], BinaryIO)` writes one line per item, each ending in `\n`. `dumps` returns the bytes. Only the given structure decides the bytes, and nothing is sorted or reordered.
- `otlp/reader.py`: `decode_line(str) -> TracesData` raises `OtlpFormatError(reason)`. The reason includes a JSON path such as `resourceSpans[0].scopeSpans[0].spans[2].traceId`. `read_lines(Iterable[bytes])` and `read_file(path)` yield `Line(line_no, data)` or `LineError(line_no, kind, reason)` for each non-blank line. `kind` is `malformed`, `logs` or `metrics`. The file is opened read-only, in binary mode.
- `otlp/__init__.py` re-exports the public names.

## Steps

- [ ] Data types and writer, with the fixed field order and the omission rules, plus the determinism test.
- [ ] Reader: value decoding, IDs, timestamps, per-line errors, logs and metrics detection, plus tests for each kind of error and for continuing past a bad line.
- [ ] Hypothesis round-trip property test over generated spans with every attribute value type.
- [ ] Outcome, verify, ship.

## Acceptance criteria

- A Hypothesis property test shows that write then read round-trips any span, including every attribute value type.
- Malformed lines give errors carrying the line number and reason. One bad line does not stop the remaining lines being read.
- Writing the same spans twice gives byte-identical output.

## Decisions

- **D1** [gap] plan M1.4 / Spec 001 section 5: Blank or whitespace-only lines are skipped and are not errors, but they still count towards line numbers. Why: files often end with a newline, and JSON Lines readers commonly allow blank lines.
- **D2** [gap] plan M1.4: A line whose object has `resourceLogs` or `resourceMetrics` and no `resourceSpans` gives a line error of kind `logs` or `metrics`. An object with none of these keys is `malformed` ("missing resourceSpans"). `"resourceSpans": []` is valid and has no spans. Why: the issue asks for logs and metrics to be detected per file, and the FR-1 AC4 exit code is decided by `validate` (#8) from these kinds.
- **D3** [gap] plan M1.4: A line gets one error, the first problem found. The error stops that line, and every other line is still read. Why: the issue requires a line number and a reason, and a single reason per line keeps output bounded.
- **D4** [gap] plan M1.4: A `traceId` must be 32 hex characters and a `spanId` 16. Missing, empty or all-zero values are errors. A link's IDs follow the same rules. `parentSpanId` may be missing or empty, for root spans, and otherwise must be 16 hex characters that are not all zero. Upper-case hex is accepted and stored lower-case. The writer always writes lower case. Why: OTLP treats empty and all-zero IDs as invalid, and spans could not be assembled without them.
- **D5** [gap] plan M1.4: Integer fields accept a JSON number or a decimal string. Timestamps and `intValue` are written as decimal strings, and 32-bit fields (`flags`, the dropped counts, `kind`, `status.code`) as numbers. Values out of range for their protobuf type are errors, and so are JSON booleans given where a number is expected. Why: this is the proto3 JSON mapping, which OTLP/JSON follows.
- **D6** [gap] plan M1.4: `doubleValue` accepts a JSON number or `"NaN"`, `"Infinity"` or `"-Infinity"`, and the writer writes those strings for non-finite values. `bytesValue` is standard base64, written with padding. Padding is optional on read. Why: this is the proto3 JSON mapping, and the output stays valid JSON.
- **D7** [gap] plan M1.4: `kind` must be 0 to 5 and `status.code` 0 to 2. Enum names given as strings are errors. Why: OTLP/JSON says enums MUST be integers. The open question is whether to accept future enum values. Strict checking makes a new value show up instead of being silently misread.
- **D8** [gap] plan M1.4: Unknown fields are ignored at every level. snake_case keys are not recognised, so they are treated as unknown fields. Why: OTLP/JSON requires both.
- **D9** [gap] plan M1.4: The writer leaves fields out when they hold their default (empty IDs and strings, zero counts and flags, empty lists, an unset status with no message, empty resource and scope). `traceId`, `spanId`, `name`, `kind`, `startTimeUnixNano` and `endTimeUnixNano` are always written. Keys are written in the order of the protobuf field numbers, with `,` and `:` as separators and non-ASCII characters left unescaped. Why: the output is compact, and a fixed form gives the byte-identical output that FR-3 AC7 later depends on.
- **D10** [gap] plan M1.4: A string containing a lone surrogate (not valid Unicode) cannot be written. The writer raises `ValueError` naming the field. Why: OTLP strings must be valid UTF-8. Cleaning up such text belongs to whoever produces the span (for Claude Code, the M3 importer), not to the serialiser.
- **D11** [gap] plan M1.4: A line that is not valid UTF-8 is a `malformed` line error. Why: OTLP/JSON is UTF-8, and one bad line must not stop the others being read.

## Verification

Standard checks. The round-trip property test runs on the unit tier, with Hypothesis's default example count. All fixtures are built in the tests from made-up values.

## Risks and open questions

- How strictly to check enums (D7) can be loosened later if real producers send newer values. The FR-2 AC2 Collector fixture (#11) is the first check against real OTLP output.

## Outcome

_Filled in before shipping._
