"""Write then read round-trips any span (plan M1.4). Generated data only."""

from __future__ import annotations

import dataclasses
import enum
import io
import math
from typing import Any

from hypothesis import given, settings
from hypothesis import strategies as st

from eagain.otlp import (
    Event,
    InstrumentationScope,
    KeyValue,
    KvList,
    Line,
    Link,
    Resource,
    ResourceSpans,
    ScopeSpans,
    Span,
    SpanKind,
    Status,
    StatusCode,
    TracesData,
    Value,
    decode_line,
    dumps,
    encode_line,
    read_lines,
)

# Valid Unicode only: lone surrogates cannot be written (work plan D10).
text = st.text(st.characters(codec="utf-8"), max_size=12)
u32 = st.integers(0, 2**32 - 1)
u64 = st.integers(0, 2**64 - 1)


def hex_id(n_bytes: int) -> st.SearchStrategy[str]:
    return st.binary(min_size=n_bytes, max_size=n_bytes).filter(any).map(bytes.hex)


def _kvlist(pairs: list[tuple[str, Value]]) -> KvList:
    return KvList(tuple(KeyValue(k, v) for k, v in pairs))


scalars: st.SearchStrategy[Value] = st.one_of(
    st.none(),
    text,
    st.booleans(),
    st.integers(-(2**63), 2**63 - 1),
    st.floats(),  # includes NaN, infinities and -0.0
    st.binary(max_size=12),
)
values: st.SearchStrategy[Value] = st.recursive(
    scalars,
    lambda inner: st.one_of(
        st.lists(inner, max_size=3).map(tuple),
        st.lists(st.tuples(text, inner), max_size=3).map(_kvlist),
    ),
    max_leaves=8,
)
attributes = st.lists(st.builds(KeyValue, text, values), max_size=4).map(tuple)

events = st.builds(
    Event,
    time_unix_nano=u64,
    name=text,
    attributes=attributes,
    dropped_attributes_count=u32,
)
links = st.builds(
    Link,
    trace_id=hex_id(16),
    span_id=hex_id(8),
    trace_state=text,
    attributes=attributes,
    dropped_attributes_count=u32,
    flags=u32,
)
spans = st.builds(
    Span,
    trace_id=hex_id(16),
    span_id=hex_id(8),
    name=text,
    trace_state=text,
    parent_span_id=st.one_of(st.just(""), hex_id(8)),
    flags=u32,
    kind=st.sampled_from(SpanKind),
    start_time_unix_nano=u64,
    end_time_unix_nano=u64,
    attributes=attributes,
    dropped_attributes_count=u32,
    events=st.lists(events, max_size=2).map(tuple),
    dropped_events_count=u32,
    links=st.lists(links, max_size=2).map(tuple),
    dropped_links_count=u32,
    status=st.builds(Status, message=text, code=st.sampled_from(StatusCode)),
)
scope_spans = st.builds(
    ScopeSpans,
    scope=st.builds(
        InstrumentationScope,
        name=text,
        version=text,
        attributes=attributes,
        dropped_attributes_count=u32,
    ),
    spans=st.lists(spans, max_size=3).map(tuple),
    schema_url=text,
)
traces_data = st.builds(
    TracesData,
    st.lists(
        st.builds(
            ResourceSpans,
            resource=st.builds(Resource, attributes=attributes, dropped_attributes_count=u32),
            scope_spans=st.lists(scope_spans, max_size=2).map(tuple),
            schema_url=text,
        ),
        max_size=2,
    ).map(tuple),
)


def canon(x: Any) -> Any:
    """A form where equal means identical: types are kept, so True != 1 and 1 != 1.0,
    NaN equals NaN, and -0.0 differs from 0.0."""
    if isinstance(x, enum.Enum):
        return (type(x).__name__, x.value)
    if isinstance(x, KeyValue):
        return ("kv", x.key, canon(x.value))
    if dataclasses.is_dataclass(x):
        return (type(x).__name__, *(canon(getattr(x, f.name)) for f in dataclasses.fields(x)))
    if isinstance(x, tuple):
        return ("tuple", *(canon(v) for v in x))
    if isinstance(x, float):
        return ("float", "nan" if math.isnan(x) else x.hex())
    return (type(x).__name__, x)


@settings(deadline=None)
@given(traces_data)
def test_write_then_read_round_trips_any_span(data: TracesData) -> None:
    line = encode_line(data)
    back = decode_line(line)
    assert canon(back) == canon(data)
    assert encode_line(back) == line


@settings(deadline=None)
@given(st.lists(traces_data, max_size=3))
def test_write_then_read_round_trips_a_whole_file(lines: list[TracesData]) -> None:
    raw = dumps(lines)
    results = list(read_lines(io.BytesIO(raw)))
    assert all(isinstance(r, Line) for r in results)
    assert [canon(r.data) for r in results if isinstance(r, Line)] == [canon(d) for d in lines]
    assert [r.line_no for r in results] == list(range(1, len(lines) + 1))


@settings(deadline=None)
@given(traces_data)
def test_writing_equal_spans_gives_identical_bytes(data: TracesData) -> None:
    # A rebuilt copy holds equal values in new objects, as a second run would.
    copy = decode_line(encode_line(data))
    assert dumps([data, data]) == dumps([copy, copy])


def test_every_attribute_value_type_round_trips() -> None:
    every: tuple[KeyValue, ...] = (
        KeyValue("string", "x"),
        KeyValue("bool", True),
        KeyValue("int", 1),
        KeyValue("double", 1.0),
        KeyValue("nan", math.nan),
        KeyValue("bytes", b"\x01"),
        KeyValue("array", ("x", False, 2, 3.5, b"", None, ())),
        KeyValue("kvlist", KvList((KeyValue("nested", KvList((KeyValue("deep", 1),))),))),
        KeyValue("empty", None),
    )
    data = TracesData(
        (
            ResourceSpans(
                scope_spans=(ScopeSpans(spans=(Span("ab" * 16, "cd" * 8, attributes=every),)),)
            ),
        )
    )
    assert canon(decode_line(encode_line(data))) == canon(data)
