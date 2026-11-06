"""Read and write OTLP JSON Lines trace files (the OTLP File format).

Each line holds one traces export object, ``{"resourceSpans": [...]}``.
"""

from __future__ import annotations

from eagain.otlp.data import (
    Attributes,
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
    Value,
)
from eagain.otlp.writer import dumps, encode_line, write_lines

__all__ = [
    "Attributes",
    "Event",
    "InstrumentationScope",
    "KeyValue",
    "KvList",
    "Link",
    "Resource",
    "ResourceSpans",
    "ScopeSpans",
    "Span",
    "SpanKind",
    "Status",
    "StatusCode",
    "TracesData",
    "Value",
    "dumps",
    "encode_line",
    "write_lines",
]
