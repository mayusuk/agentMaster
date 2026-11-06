"""OTLP JSON Lines reader (plan M1.4). All values are made up."""

from __future__ import annotations

import hashlib
import json
import math
import stat
from pathlib import Path
from typing import Any

import pytest

from eagain.otlp import (
    ErrorKind,
    KeyValue,
    KvList,
    Line,
    LineError,
    OtlpFormatError,
    SpanKind,
    StatusCode,
    decode_line,
    read_file,
    read_lines,
)

TRACE = "0af7651916cd43dd8448eb211c80319c"
SPAN = "b7ad6b7169203331"
PARENT = "00f067aa0ba902b7"


def span(**fields: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"traceId": TRACE, "spanId": SPAN, "name": "s"}
    base.update(fields)
    return {k: v for k, v in base.items() if v is not ...}


def line_with(*spans: dict[str, Any]) -> str:
    return json.dumps({"resourceSpans": [{"scopeSpans": [{"spans": list(spans)}]}]})


def attr_line(value: Any) -> str:
    return line_with(span(attributes=[{"key": "k", "value": value}]))


def first_attr(text: str) -> object:
    _, _, s = decode_line(text).spans()[0]
    return s.attributes[0].value


def reason(text: str) -> str:
    with pytest.raises(OtlpFormatError) as exc:
        decode_line(text)
    return exc.value.reason


# --- Decoding valid lines -----------------------------------------------------------


def test_decodes_a_full_line() -> None:
    text = json.dumps(
        {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [{"key": "service.name", "value": {"stringValue": "demo"}}]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "demo-scope", "version": "0.1"},
                            "spans": [
                                {
                                    "traceId": TRACE,
                                    "spanId": SPAN,
                                    "parentSpanId": PARENT,
                                    "name": "execute_tool demo",
                                    "kind": 3,
                                    "startTimeUnixNano": "1700000000000000000",
                                    "endTimeUnixNano": "1700000001000000000",
                                    "events": [
                                        {"timeUnixNano": "1700000000500000000", "name": "e"}
                                    ],
                                    "links": [{"traceId": TRACE, "spanId": PARENT, "flags": 1}],
                                    "status": {"message": "boom", "code": 2},
                                    "flags": 257,
                                }
                            ],
                        }
                    ],
                    "schemaUrl": "https://example.invalid/schema",
                }
            ]
        }
    )
    data = decode_line(text)
    [(resource, scope, s)] = data.spans()
    assert resource.attributes == (KeyValue("service.name", "demo"),)
    assert (scope.name, scope.version) == ("demo-scope", "0.1")
    assert data.resource_spans[0].schema_url == "https://example.invalid/schema"
    assert (s.trace_id, s.span_id, s.parent_span_id) == (TRACE, SPAN, PARENT)
    assert s.kind is SpanKind.CLIENT
    assert s.start_time_unix_nano == 1_700_000_000_000_000_000
    assert s.end_time_unix_nano == 1_700_000_001_000_000_000
    assert s.events[0].time_unix_nano == 1_700_000_000_500_000_000
    assert s.links[0].span_id == PARENT
    assert s.links[0].flags == 1
    assert s.status.code is StatusCode.ERROR
    assert s.status.message == "boom"
    assert s.flags == 257


def test_decodes_every_attribute_value_type() -> None:
    assert first_attr(attr_line({"stringValue": "héllo"})) == "héllo"
    assert first_attr(attr_line({"boolValue": False})) is False
    assert first_attr(attr_line({"intValue": "-9223372036854775808"})) == -(2**63)
    assert first_attr(attr_line({"intValue": 7})) == 7
    assert first_attr(attr_line({"doubleValue": 2.5})) == 2.5
    assert first_attr(attr_line({"bytesValue": "AP8="})) == b"\x00\xff"
    assert first_attr(attr_line({"arrayValue": {"values": [{"intValue": "1"}, {}]}})) == (1, None)
    assert first_attr(
        attr_line({"kvlistValue": {"values": [{"key": "a", "value": {"boolValue": True}}]}})
    ) == KvList((KeyValue("a", True),))
    assert first_attr(attr_line({"arrayValue": {}})) == ()
    assert first_attr(attr_line({"kvlistValue": {}})) == KvList()
    assert first_attr(attr_line({})) is None


def test_int_value_type_is_kept_distinct_from_bool_and_double() -> None:
    assert type(first_attr(attr_line({"intValue": "1"}))) is int
    assert type(first_attr(attr_line({"boolValue": True}))) is bool
    double = first_attr(attr_line({"doubleValue": 1}))
    assert type(double) is float
    assert double == 1.0


@pytest.mark.parametrize(
    ("encoded", "check"),
    [
        ("NaN", math.isnan),
        ("Infinity", lambda v: v == math.inf),
        ("-Infinity", lambda v: v == -math.inf),
    ],
)
def test_non_finite_doubles_from_strings(encoded: str, check: Any) -> None:
    assert check(first_attr(attr_line({"doubleValue": encoded})))


def test_base64_padding_is_optional() -> None:
    assert first_attr(attr_line({"bytesValue": "AP8"})) == b"\x00\xff"


def test_timestamps_accept_numbers_and_strings() -> None:
    _, _, s = decode_line(
        line_with(span(startTimeUnixNano=5, endTimeUnixNano="18446744073709551615"))
    ).spans()[0]
    assert s.start_time_unix_nano == 5
    assert s.end_time_unix_nano == 2**64 - 1


def test_upper_case_hex_ids_are_stored_lower_case() -> None:
    _, _, s = decode_line(
        line_with(span(traceId=TRACE.upper(), spanId=SPAN.upper(), parentSpanId=PARENT.upper()))
    ).spans()[0]
    assert (s.trace_id, s.span_id, s.parent_span_id) == (TRACE, SPAN, PARENT)


def test_missing_optional_fields_take_defaults() -> None:
    _, _, s = decode_line(line_with({"traceId": TRACE, "spanId": SPAN})).spans()[0]
    assert s.name == ""
    assert s.parent_span_id == ""
    assert s.kind is SpanKind.UNSPECIFIED
    assert s.status.code is StatusCode.UNSET
    assert s.attributes == ()
    assert (s.start_time_unix_nano, s.flags, s.dropped_events_count) == (0, 0, 0)


def test_null_means_absent() -> None:
    _, _, s = decode_line(
        line_with(span(parentSpanId=None, attributes=None, status=None, kind=None))
    ).spans()[0]
    assert s.parent_span_id == ""
    assert s.attributes == ()


def test_unknown_fields_are_ignored() -> None:
    text = json.dumps(
        {
            "resourceSpans": [
                {
                    "futureField": {"x": 1},
                    "scopeSpans": [{"spans": [span(somethingNew=[1, 2], parent_span_id="zz")]}],
                }
            ],
            "extra": True,
        }
    )
    _, _, s = decode_line(text).spans()[0]
    assert s.parent_span_id == ""


def test_empty_resource_spans_is_valid() -> None:
    assert decode_line('{"resourceSpans":[]}').spans() == ()


def test_snake_case_keys_are_not_recognised() -> None:
    assert "traceId: required" in reason(
        line_with({"trace_id": TRACE, "span_id": SPAN})  # snake_case is not OTLP/JSON
    )


# --- Errors ---------------------------------------------------------------------------

SPAN_PATH = "resourceSpans[0].scopeSpans[0].spans[0]"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('{"resourceSpans": [', "invalid JSON"),
        ("[1, 2]", "expected a JSON object, got array"),
        ("{}", "missing resourceSpans"),
        ('{"resourceSpans": {}}', "resourceSpans: expected an array, got object"),
        ('{"resourceSpans": [1]}', "resourceSpans[0]: expected an object, got number"),
        (line_with(span(traceId=...)), f"{SPAN_PATH}.traceId: required"),
        (line_with(span(traceId="")), f"{SPAN_PATH}.traceId: required"),
        (line_with(span(traceId="abc")), f"{SPAN_PATH}.traceId: expected 32 hex characters"),
        (line_with(span(traceId="g" * 32)), f"{SPAN_PATH}.traceId: expected 32 hex characters"),
        (line_with(span(traceId="0" * 32)), f"{SPAN_PATH}.traceId: all zeros"),
        (line_with(span(traceId=12)), f"{SPAN_PATH}.traceId: expected a hex string, got number"),
        (line_with(span(spanId=...)), f"{SPAN_PATH}.spanId: required"),
        (line_with(span(spanId=TRACE)), f"{SPAN_PATH}.spanId: expected 16 hex characters"),
        (line_with(span(parentSpanId="0" * 16)), f"{SPAN_PATH}.parentSpanId: all zeros"),
        (line_with(span(parentSpanId="xyz")), f"{SPAN_PATH}.parentSpanId: expected 16 hex"),
        (line_with(span(name=5)), f"{SPAN_PATH}.name: expected a string, got number"),
        (line_with(span(kind="SPAN_KIND_CLIENT")), f"{SPAN_PATH}.kind: expected an integer enum"),
        (line_with(span(kind=9)), f"{SPAN_PATH}.kind: unknown value 9"),
        (line_with(span(kind=True)), f"{SPAN_PATH}.kind: expected an integer enum"),
        (line_with(span(status={"code": 3})), f"{SPAN_PATH}.status.code: unknown value 3"),
        (line_with(span(status=[])), f"{SPAN_PATH}.status: expected an object, got array"),
        (line_with(span(startTimeUnixNano=-1)), f"{SPAN_PATH}.startTimeUnixNano: integer out"),
        (
            line_with(span(endTimeUnixNano=str(2**64))),
            f"{SPAN_PATH}.endTimeUnixNano: integer out of range",
        ),
        (line_with(span(startTimeUnixNano=1.5)), f"{SPAN_PATH}.startTimeUnixNano: expected an in"),
        (line_with(span(startTimeUnixNano="1e9")), f"{SPAN_PATH}.startTimeUnixNano: expected an"),
        (line_with(span(flags=True)), f"{SPAN_PATH}.flags: expected an integer, got boolean"),
        (line_with(span(flags=2**32)), f"{SPAN_PATH}.flags: integer out of range"),
        (line_with(span(events=[5])), f"{SPAN_PATH}.events[0]: expected an object, got number"),
        (
            line_with(span(links=[{"traceId": TRACE}])),
            f"{SPAN_PATH}.links[0].spanId: required",
        ),
        (
            attr_line({"intValue": str(2**63)}),
            f"{SPAN_PATH}.attributes[0].value.intValue: integer out of range",
        ),
        (attr_line({"boolValue": "true"}), "value.boolValue: expected a boolean, got string"),
        (attr_line({"stringValue": 3}), "value.stringValue: expected a string, got number"),
        (attr_line({"doubleValue": "1.5"}), "value.doubleValue: expected a number, NaN"),
        (attr_line({"doubleValue": True}), "value.doubleValue: expected a number, got boolean"),
        (attr_line({"bytesValue": "***"}), "value.bytesValue: not valid base64"),
        (attr_line({"bytesValue": 1}), "value.bytesValue: expected a base64 string"),
        (
            attr_line({"stringValue": "a", "intValue": "1"}),
            "value: more than one value field set (stringValue, intValue)",
        ),
        (attr_line({"arrayValue": []}), "value.arrayValue: expected an object, got array"),
        (attr_line({"arrayValue": {"values": [3]}}), "arrayValue.values[0]: expected an object"),
        (attr_line("x"), f"{SPAN_PATH}.attributes[0].value: expected an object, got string"),
        ('{"resourceSpans": [], "x": NaN}', "invalid JSON: NaN is not a JSON value"),
    ],
)
def test_malformed_lines_give_a_reason_with_the_path(text: str, expected: str) -> None:
    with pytest.raises(OtlpFormatError) as exc:
        decode_line(text)
    assert exc.value.kind is ErrorKind.MALFORMED
    assert expected in exc.value.reason


def test_deeply_nested_values_are_an_error_not_a_crash() -> None:
    # Built as text, because json.dumps itself hits the recursion limit on Python 3.11.
    depth = 400
    value = '{"arrayValue":{"values":[' * depth + '{"stringValue":"x"}' + "]}}" * depth
    deep = attr_line({"stringValue": "PLACEHOLDER"}).replace(
        '{"stringValue": "PLACEHOLDER"}', value
    )
    assert "nested too deeply" in reason(deep)
    # Python 3.11 hits its recursion limit inside json; newer versions parse this.
    n = 200_000
    assert reason("[" * n + "]" * n) in (
        "invalid JSON: nested too deeply",
        "expected a JSON object, got array",
    )


def test_reasons_never_repeat_line_content() -> None:
    planted = "SECRETPLANTEDVALUE"
    for text in (
        line_with(span(traceId=planted)),
        attr_line({"intValue": planted}),
        attr_line({"doubleValue": planted}),
        attr_line({"bytesValue": planted + "!"}),
        '{"resourceSpans": [' + planted,
    ):
        assert planted not in reason(text)


def test_logs_and_metrics_lines_are_reported_as_such() -> None:
    with pytest.raises(OtlpFormatError) as logs:
        decode_line('{"resourceLogs": []}')
    assert logs.value.kind is ErrorKind.LOGS
    assert "only traces are supported" in logs.value.reason
    with pytest.raises(OtlpFormatError) as metrics:
        decode_line('{"resourceMetrics": [{}]}')
    assert metrics.value.kind is ErrorKind.METRICS
    assert "only traces are supported" in metrics.value.reason


def test_a_line_with_resource_spans_is_traces_even_with_other_signals() -> None:
    assert decode_line('{"resourceSpans": [], "resourceLogs": []}').spans() == ()


# --- Reading many lines -------------------------------------------------------------------


def test_errors_carry_line_numbers_and_reading_continues_after_a_bad_line() -> None:
    good = line_with(span()).encode()
    lines = [
        good,
        b'{"resourceSpans": [',
        good,
        b"",
        b"   \r",
        b'{"resourceLogs": []}',
        b'{"resourceMetrics": []}',
        b"\xff\xfe not utf-8",
        good,
    ]
    results = list(read_lines(lines))
    assert [(type(r).__name__, r.line_no) for r in results] == [
        ("Line", 1),
        ("LineError", 2),
        ("Line", 3),
        ("LineError", 6),
        ("LineError", 7),
        ("LineError", 8),
        ("Line", 9),
    ]
    errors = [r for r in results if isinstance(r, LineError)]
    assert [e.kind for e in errors] == [
        ErrorKind.MALFORMED,
        ErrorKind.LOGS,
        ErrorKind.METRICS,
        ErrorKind.MALFORMED,
    ]
    assert errors[0].reason.startswith("invalid JSON")
    assert errors[3].reason == "not valid UTF-8 at byte 0"


def test_read_file_streams_lines_and_leaves_the_file_unchanged(tmp_path: Path) -> None:
    path = tmp_path / "traces.jsonl"
    good = line_with(span())
    path.write_bytes(f"{good}\n\nnot json\r\n{good}".encode())
    path.chmod(stat.S_IRUSR)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    results = list(read_file(path))
    assert [r.line_no for r in results] == [1, 3, 4]
    assert isinstance(results[0], Line)
    assert isinstance(results[1], LineError)
    assert isinstance(results[2], Line)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before
