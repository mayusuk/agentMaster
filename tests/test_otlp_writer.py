"""OTLP JSON Lines writer (plan M1.4). All values are made up."""

from __future__ import annotations

import io
import json

import pytest

from eagain.otlp import (
    Event,
    InstrumentationScope,
    KeyValue,
    KvList,
    Link,
    Resource,
    ResourceSpans,
    ScopeSpans,
    Span,
    SpanKind,
    Status,
    StatusCode,
    TracesData,
    dumps,
    encode_line,
    write_lines,
)

TRACE = "0af7651916cd43dd8448eb211c80319c"
ROOT = "b7ad6b7169203331"
CHILD = "00f067aa0ba902b7"


def sample() -> list[TracesData]:
    root = Span(
        trace_id=TRACE,
        span_id=ROOT,
        name="invoke_agent demo",
        kind=SpanKind.INTERNAL,
        start_time_unix_nano=1_700_000_000_000_000_000,
        end_time_unix_nano=1_700_000_005_000_000_000,
        attributes=(KeyValue("gen_ai.operation.name", "invoke_agent"),),
    )
    child = Span(
        trace_id=TRACE,
        span_id=CHILD,
        parent_span_id=ROOT,
        name="execute_tool read_file",
        kind=SpanKind.INTERNAL,
        start_time_unix_nano=1_700_000_001_000_000_000,
        end_time_unix_nano=1_700_000_002_000_000_000,
        attributes=(
            KeyValue("s", "héllo"),
            KeyValue("b", True),
            KeyValue("i", -42),
            KeyValue("d", 1.5),
            KeyValue("a", ("x", 1)),
            KeyValue("k", KvList((KeyValue("inner", False),))),
            KeyValue("y", b"\x00\xff"),
            KeyValue("n", None),
        ),
        events=(Event(time_unix_nano=1_700_000_001_500_000_000, name="exception"),),
        links=(Link(trace_id=TRACE, span_id=ROOT),),
        status=Status(message="File not found: /tmp/x", code=StatusCode.ERROR),
        flags=1,
    )
    rs = ResourceSpans(
        resource=Resource(attributes=(KeyValue("service.name", "demo-agent"),)),
        scope_spans=(
            ScopeSpans(scope=InstrumentationScope(name="demo", version="1"), spans=(root, child)),
        ),
    )
    return [TracesData((rs,))]


def test_writing_same_spans_twice_is_byte_identical() -> None:
    assert dumps(sample()) == dumps(sample())
    out = io.BytesIO()
    write_lines(sample(), out)
    assert out.getvalue() == dumps(sample())


def test_output_has_one_line_per_traces_data_ending_in_newline() -> None:
    data = sample() * 3
    raw = dumps(data)
    assert raw.endswith(b"\n")
    lines = raw.decode("utf-8").split("\n")
    assert lines[-1] == ""
    assert len(lines[:-1]) == 3
    for line in lines[:-1]:
        assert set(json.loads(line)) == {"resourceSpans"}


def test_fixed_key_order_and_compact_separators() -> None:
    line = encode_line(sample()[0])
    compact = json.dumps(json.loads(line), ensure_ascii=False, separators=(",", ":"))
    assert line == compact
    span = json.loads(line)["resourceSpans"][0]["scopeSpans"][0]["spans"][1]
    assert list(span) == [
        "traceId",
        "spanId",
        "parentSpanId",
        "name",
        "kind",
        "startTimeUnixNano",
        "endTimeUnixNano",
        "attributes",
        "events",
        "links",
        "status",
        "flags",
    ]
    assert list(span["status"]) == ["message", "code"]


def test_encodes_every_attribute_value_type() -> None:
    span = json.loads(encode_line(sample()[0]))["resourceSpans"][0]["scopeSpans"][0]["spans"][1]
    values = {kv["key"]: kv["value"] for kv in span["attributes"]}
    assert values == {
        "s": {"stringValue": "héllo"},
        "b": {"boolValue": True},
        "i": {"intValue": "-42"},
        "d": {"doubleValue": 1.5},
        "a": {"arrayValue": {"values": [{"stringValue": "x"}, {"intValue": "1"}]}},
        "k": {"kvlistValue": {"values": [{"key": "inner", "value": {"boolValue": False}}]}},
        "y": {"bytesValue": "AP8="},
        "n": {},
    }


def test_non_ascii_is_written_as_utf8_not_escaped() -> None:
    assert "héllo".encode() in dumps(sample())


def test_timestamps_are_decimal_strings() -> None:
    span = json.loads(encode_line(sample()[0]))["resourceSpans"][0]["scopeSpans"][0]["spans"][0]
    assert span["startTimeUnixNano"] == "1700000000000000000"
    assert span["endTimeUnixNano"] == "1700000005000000000"


def test_default_fields_are_omitted_but_required_span_fields_kept() -> None:
    spans = ScopeSpans(spans=(Span(trace_id=TRACE, span_id=ROOT),))
    line = encode_line(TracesData((ResourceSpans(scope_spans=(spans,)),)))
    assert json.loads(line) == {
        "resourceSpans": [
            {
                "scopeSpans": [
                    {
                        "spans": [
                            {
                                "traceId": TRACE,
                                "spanId": ROOT,
                                "name": "",
                                "kind": 0,
                                "startTimeUnixNano": "0",
                                "endTimeUnixNano": "0",
                            }
                        ]
                    }
                ]
            }
        ]
    }


def test_empty_traces_data_writes_empty_resource_spans() -> None:
    assert encode_line(TracesData()) == '{"resourceSpans":[]}'


@pytest.mark.parametrize(
    ("value", "encoded"),
    [(float("nan"), "NaN"), (float("inf"), "Infinity"), (float("-inf"), "-Infinity")],
)
def test_non_finite_doubles_are_strings(value: float, encoded: str) -> None:
    rs = ResourceSpans(resource=Resource(attributes=(KeyValue("d", value),)))
    obj = json.loads(encode_line(TracesData((rs,))))
    assert obj["resourceSpans"][0]["resource"]["attributes"][0]["value"] == {"doubleValue": encoded}


def test_empty_array_and_kvlist() -> None:
    rs = ResourceSpans(resource=Resource(attributes=(KeyValue("a", ()), KeyValue("k", KvList()))))
    attrs = json.loads(encode_line(TracesData((rs,))))["resourceSpans"][0]["resource"]["attributes"]
    assert [kv["value"] for kv in attrs] == [{"arrayValue": {}}, {"kvlistValue": {}}]


def test_int_outside_int64_is_rejected() -> None:
    rs = ResourceSpans(resource=Resource(attributes=(KeyValue("i", 2**63),)))
    with pytest.raises(ValueError, match="64-bit"):
        encode_line(TracesData((rs,)))


def test_lone_surrogate_is_rejected_with_its_path() -> None:
    rs = ResourceSpans(resource=Resource(attributes=(KeyValue("s", "bad\ud800"),)))
    with pytest.raises(ValueError, match=r"resourceSpans\[0\]\.resource\.attributes\[0\]") as exc:
        encode_line(TracesData((rs,)))
    assert "bad" not in str(exc.value)
