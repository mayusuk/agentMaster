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
from eagain.otlp.reader import (
    ErrorKind,
    Line,
    LineError,
    OtlpFormatError,
    decode_line,
    read_file,
    read_lines,
)
from eagain.otlp.writer import dumps, encode_line, write_lines

__all__ = [
    "Attributes",
    "ErrorKind",
    "Event",
    "InstrumentationScope",
    "KeyValue",
    "KvList",
    "Line",
    "LineError",
    "Link",
    "OtlpFormatError",
    "Resource",
    "ResourceSpans",
    "ScopeSpans",
    "Span",
    "SpanKind",
    "Status",
    "StatusCode",
    "TracesData",
    "Value",
    "decode_line",
    "dumps",
    "encode_line",
    "read_file",
    "read_lines",
    "write_lines",
]
