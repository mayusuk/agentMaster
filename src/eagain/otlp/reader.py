"""OTLP JSON Lines reader.

Each non-blank line must hold one traces export object, ``{"resourceSpans": [...]}``,
in the OTLP/JSON encoding:

- keys are lowerCamelCase, and unknown keys are ignored at every level;
- ``null`` means the field is absent;
- trace and span IDs are hex (any case, stored lower-case). ``traceId`` and
  ``spanId`` are required and must not be all zeros;
- integers may be JSON numbers or decimal strings, and must fit their protobuf
  type. Enums (``kind``, ``status.code``) must be integers;
- ``doubleValue`` may also be ``"NaN"``, ``"Infinity"`` or ``"-Infinity"``, and
  ``bytesValue`` is standard base64 with optional padding.

Problems are reported per line as a :class:`LineError` with its 1-based line
number and a reason, and reading carries on with the next line. Reasons name
the JSON path of the problem but never repeat the line's content, because that
content may be untrusted transcript text. Lines that hold logs or metrics
instead of traces get their own error kinds.
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from pathlib import Path
from typing import Any, TypeVar

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


class ErrorKind(StrEnum):
    MALFORMED = "malformed"
    LOGS = "logs"
    METRICS = "metrics"


class OtlpFormatError(ValueError):
    def __init__(self, reason: str, kind: ErrorKind = ErrorKind.MALFORMED) -> None:
        super().__init__(reason)
        self.reason = reason
        self.kind = kind


@dataclass(frozen=True, slots=True)
class Line:
    line_no: int
    data: TracesData


@dataclass(frozen=True, slots=True)
class LineError:
    line_no: int
    kind: ErrorKind
    reason: str


def read_file(path: str | Path) -> Iterator[Line | LineError]:
    """Read a file one line at a time. The file is opened read-only."""
    with open(path, "rb") as f:
        yield from read_lines(f)


def read_lines(lines: Iterable[bytes]) -> Iterator[Line | LineError]:
    """Decode raw lines, skipping blank ones. Line numbers count every line."""
    for line_no, raw in enumerate(lines, start=1):
        if not raw.strip():
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as e:
            yield LineError(line_no, ErrorKind.MALFORMED, f"not valid UTF-8 at byte {e.start}")
            continue
        try:
            yield Line(line_no, decode_line(text))
        except OtlpFormatError as e:
            yield LineError(line_no, e.kind, e.reason)


def decode_line(text: str) -> TracesData:
    """Decode one line. Raises :class:`OtlpFormatError` on any problem."""
    try:
        obj = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as e:
        raise OtlpFormatError(f"invalid JSON: {e.msg} at column {e.colno}") from None
    except RecursionError:
        raise OtlpFormatError("invalid JSON: nested too deeply") from None
    if not isinstance(obj, dict):
        raise OtlpFormatError(f"expected a JSON object, got {_type_name(obj)}")
    if obj.get("resourceSpans") is None:
        if obj.get("resourceLogs") is not None:
            raise OtlpFormatError(
                "this line holds OTLP logs; only traces are supported", ErrorKind.LOGS
            )
        if obj.get("resourceMetrics") is not None:
            raise OtlpFormatError(
                "this line holds OTLP metrics; only traces are supported", ErrorKind.METRICS
            )
        raise OtlpFormatError("missing resourceSpans")
    try:
        return TracesData(_list(obj, "resourceSpans", "", _resource_spans))
    except RecursionError:
        raise OtlpFormatError("attribute values nested too deeply") from None


def _reject_constant(name: str) -> object:
    raise OtlpFormatError(f"invalid JSON: {name} is not a JSON value")


# --- Messages -----------------------------------------------------------------------

T = TypeVar("T")
E = TypeVar("E", bound=IntEnum)
JsonObject = dict[str, Any]


def _resource_spans(o: JsonObject, p: str) -> ResourceSpans:
    return ResourceSpans(
        resource=_message(o, "resource", p, _resource, Resource()),
        scope_spans=_list(o, "scopeSpans", p, _scope_spans),
        schema_url=_str(o, "schemaUrl", p),
    )


def _resource(o: JsonObject, p: str) -> Resource:
    return Resource(
        attributes=_attributes(o, p),
        dropped_attributes_count=_uint(o, "droppedAttributesCount", p, 32),
    )


def _scope_spans(o: JsonObject, p: str) -> ScopeSpans:
    return ScopeSpans(
        scope=_message(o, "scope", p, _scope, InstrumentationScope()),
        spans=_list(o, "spans", p, _span),
        schema_url=_str(o, "schemaUrl", p),
    )


def _scope(o: JsonObject, p: str) -> InstrumentationScope:
    return InstrumentationScope(
        name=_str(o, "name", p),
        version=_str(o, "version", p),
        attributes=_attributes(o, p),
        dropped_attributes_count=_uint(o, "droppedAttributesCount", p, 32),
    )


def _span(o: JsonObject, p: str) -> Span:
    return Span(
        trace_id=_id(o, "traceId", p, 16, required=True),
        span_id=_id(o, "spanId", p, 8, required=True),
        trace_state=_str(o, "traceState", p),
        parent_span_id=_id(o, "parentSpanId", p, 8, required=False),
        flags=_uint(o, "flags", p, 32),
        name=_str(o, "name", p),
        kind=_enum(o, "kind", p, SpanKind),
        start_time_unix_nano=_uint(o, "startTimeUnixNano", p, 64),
        end_time_unix_nano=_uint(o, "endTimeUnixNano", p, 64),
        attributes=_attributes(o, p),
        dropped_attributes_count=_uint(o, "droppedAttributesCount", p, 32),
        events=_list(o, "events", p, _event),
        dropped_events_count=_uint(o, "droppedEventsCount", p, 32),
        links=_list(o, "links", p, _link),
        dropped_links_count=_uint(o, "droppedLinksCount", p, 32),
        status=_message(o, "status", p, _status, Status()),
    )


def _event(o: JsonObject, p: str) -> Event:
    return Event(
        time_unix_nano=_uint(o, "timeUnixNano", p, 64),
        name=_str(o, "name", p),
        attributes=_attributes(o, p),
        dropped_attributes_count=_uint(o, "droppedAttributesCount", p, 32),
    )


def _link(o: JsonObject, p: str) -> Link:
    return Link(
        trace_id=_id(o, "traceId", p, 16, required=True),
        span_id=_id(o, "spanId", p, 8, required=True),
        trace_state=_str(o, "traceState", p),
        attributes=_attributes(o, p),
        dropped_attributes_count=_uint(o, "droppedAttributesCount", p, 32),
        flags=_uint(o, "flags", p, 32),
    )


def _status(o: JsonObject, p: str) -> Status:
    return Status(message=_str(o, "message", p), code=_enum(o, "code", p, StatusCode))


# --- Attributes and values -------------------------------------------------------------

_VALUE_KEYS = (
    "stringValue",
    "boolValue",
    "intValue",
    "doubleValue",
    "arrayValue",
    "kvlistValue",
    "bytesValue",
)
_NON_FINITE = {"NaN": float("nan"), "Infinity": float("inf"), "-Infinity": float("-inf")}


def _attributes(o: JsonObject, p: str) -> Attributes:
    return _list(o, "attributes", p, _key_value)


def _key_value(o: JsonObject, p: str) -> KeyValue:
    return KeyValue(_str(o, "key", p), _message(o, "value", p, _any_value, None))


def _any_value(o: JsonObject, p: str) -> Value:
    present = [k for k in _VALUE_KEYS if o.get(k) is not None]
    if not present:
        return None
    if len(present) > 1:
        raise OtlpFormatError(f"{p}: more than one value field set ({', '.join(present)})")
    key = present[0]
    v = o[key]
    q = _join(p, key)
    if key == "stringValue":
        return _str(o, key, p)
    if key == "boolValue":
        if not isinstance(v, bool):
            raise OtlpFormatError(f"{q}: expected a boolean, got {_type_name(v)}")
        return v
    if key == "intValue":
        return _int(v, q, -(2**63), 2**63 - 1)
    if key == "doubleValue":
        return _double(v, q)
    if key == "arrayValue":
        empty: tuple[Value, ...] = ()
        return _message(o, key, p, lambda a, ap: _list(a, "values", ap, _any_value), empty)
    if key == "kvlistValue":
        return _message(
            o, key, p, lambda a, ap: KvList(_list(a, "values", ap, _key_value)), KvList()
        )
    return _bytes(v, q)


def _double(v: object, p: str) -> float:
    if isinstance(v, str):
        if v in _NON_FINITE:
            return _NON_FINITE[v]
        raise OtlpFormatError(f"{p}: expected a number, NaN, Infinity or -Infinity")
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise OtlpFormatError(f"{p}: expected a number, got {_type_name(v)}")
    return float(v)


def _bytes(v: object, p: str) -> bytes:
    if not isinstance(v, str):
        raise OtlpFormatError(f"{p}: expected a base64 string, got {_type_name(v)}")
    try:
        return base64.b64decode(v + "=" * (-len(v) % 4), validate=True)
    except (binascii.Error, ValueError):
        raise OtlpFormatError(f"{p}: not valid base64") from None


# --- Field helpers -------------------------------------------------------------------

_HEX = re.compile(r"[0-9a-fA-F]*")
_DECIMAL = re.compile(r"-?[0-9]+")


def _join(p: str, key: str) -> str:
    return f"{p}.{key}" if p else key


def _type_name(v: object) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, int | float):
        return "number"
    if isinstance(v, str):
        return "string"
    if isinstance(v, list):
        return "array"
    return "object"


def _message(
    o: JsonObject, key: str, p: str, parse: Callable[[JsonObject, str], T], default: T
) -> T:
    v = o.get(key)
    if v is None:
        return default
    q = _join(p, key)
    if not isinstance(v, dict):
        raise OtlpFormatError(f"{q}: expected an object, got {_type_name(v)}")
    return parse(v, q)


def _list(o: JsonObject, key: str, p: str, parse: Callable[[JsonObject, str], T]) -> tuple[T, ...]:
    v = o.get(key)
    if v is None:
        return ()
    q = _join(p, key)
    if not isinstance(v, list):
        raise OtlpFormatError(f"{q}: expected an array, got {_type_name(v)}")
    out: list[T] = []
    for i, item in enumerate(v):
        if not isinstance(item, dict):
            raise OtlpFormatError(f"{q}[{i}]: expected an object, got {_type_name(item)}")
        out.append(parse(item, f"{q}[{i}]"))
    return tuple(out)


def _str(o: JsonObject, key: str, p: str) -> str:
    v = o.get(key)
    if v is None:
        return ""
    if not isinstance(v, str):
        raise OtlpFormatError(f"{_join(p, key)}: expected a string, got {_type_name(v)}")
    return v


def _int(v: object, p: str, lo: int, hi: int) -> int:
    if isinstance(v, str) and _DECIMAL.fullmatch(v):
        n = int(v)
    elif isinstance(v, int) and not isinstance(v, bool):
        n = v
    else:
        raise OtlpFormatError(f"{p}: expected an integer, got {_type_name(v)}")
    if not lo <= n <= hi:
        raise OtlpFormatError(f"{p}: integer out of range")
    return n


def _uint(o: JsonObject, key: str, p: str, bits: int) -> int:
    v = o.get(key)
    if v is None:
        return 0
    return _int(v, _join(p, key), 0, 2**bits - 1)


def _enum(o: JsonObject, key: str, p: str, enum: type[E]) -> E:
    v = o.get(key)
    if v is None:
        return enum(0)
    q = _join(p, key)
    if isinstance(v, bool) or not isinstance(v, int):
        raise OtlpFormatError(f"{q}: expected an integer enum value, got {_type_name(v)}")
    try:
        return enum(v)
    except ValueError:
        raise OtlpFormatError(f"{q}: unknown value {v}") from None


def _id(o: JsonObject, key: str, p: str, n_bytes: int, *, required: bool) -> str:
    v = o.get(key)
    q = _join(p, key)
    if v is None or v == "":
        if required:
            raise OtlpFormatError(f"{q}: required")
        return ""
    if not isinstance(v, str):
        raise OtlpFormatError(f"{q}: expected a hex string, got {_type_name(v)}")
    if len(v) != 2 * n_bytes or not _HEX.fullmatch(v):
        raise OtlpFormatError(f"{q}: expected {2 * n_bytes} hex characters")
    if v.strip("0") == "":
        raise OtlpFormatError(f"{q}: all zeros is not a valid ID")
    return v.lower()
