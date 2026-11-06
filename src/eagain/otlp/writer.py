"""Deterministic OTLP JSON Lines writer.

The same data always gives the same bytes:

- keys are written in protobuf field-number order;
- fields holding their default value are left out, except ``traceId``,
  ``spanId``, ``name``, ``kind`` and the two span timestamps, which are always
  written;
- separators are ``,`` and ``:``, with no spaces, and non-ASCII text is written
  as UTF-8, not escaped;
- IDs must be lower-case hex, and values the reader would reject raise
  ``ValueError``;
- 64-bit integers (timestamps, ``intValue``) are decimal strings, and 32-bit
  integers are JSON numbers, as in the proto3 JSON mapping;
- non-finite doubles are written as ``"NaN"``, ``"Infinity"`` and
  ``"-Infinity"``, and bytes as padded standard base64.

Nothing is sorted or regrouped. Callers that need a canonical order put the
data in that order first.
"""

from __future__ import annotations

import base64
import json
import math
import re
from collections.abc import Iterable
from typing import IO, Any

from eagain.otlp.data import (
    Attributes,
    Event,
    InstrumentationScope,
    KvList,
    Link,
    Resource,
    ResourceSpans,
    ScopeSpans,
    Span,
    Status,
    StatusCode,
    TracesData,
    Value,
)

_INT64_MIN = -(2**63)
_INT64_MAX = 2**63 - 1
_HEX = re.compile(r"[0-9a-f]+")

JsonObject = dict[str, Any]


def encode_line(data: TracesData) -> str:
    """Encode one line, without its trailing newline."""
    obj = {"resourceSpans": [_resource_spans(rs) for rs in data.resource_spans]}
    text = json.dumps(obj, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        raise ValueError(
            f"{_bad_string_path(obj, '')}: string is not valid Unicode (lone surrogate)"
        ) from None
    return text


def dumps(lines: Iterable[TracesData]) -> bytes:
    """Encode lines as OTLP JSON Lines bytes, each line ending in ``\\n``."""
    return b"".join((encode_line(d) + "\n").encode("utf-8") for d in lines)


def write_lines(lines: Iterable[TracesData], out: IO[bytes]) -> None:
    """Write lines to a binary stream, one encoded line at a time."""
    for d in lines:
        out.write((encode_line(d) + "\n").encode("utf-8"))


# --- Messages, in protobuf field-number order -----------------------------------


def _resource_spans(rs: ResourceSpans) -> JsonObject:
    obj: JsonObject = {}
    resource = _resource(rs.resource)
    if resource:
        obj["resource"] = resource
    if rs.scope_spans:
        obj["scopeSpans"] = [_scope_spans(ss) for ss in rs.scope_spans]
    if rs.schema_url:
        obj["schemaUrl"] = rs.schema_url
    return obj


def _resource(r: Resource) -> JsonObject:
    obj: JsonObject = {}
    _put_attributes(obj, r.attributes, r.dropped_attributes_count)
    return obj


def _scope_spans(ss: ScopeSpans) -> JsonObject:
    obj: JsonObject = {}
    scope = _scope(ss.scope)
    if scope:
        obj["scope"] = scope
    if ss.spans:
        obj["spans"] = [_span(s) for s in ss.spans]
    if ss.schema_url:
        obj["schemaUrl"] = ss.schema_url
    return obj


def _scope(s: InstrumentationScope) -> JsonObject:
    obj: JsonObject = {}
    if s.name:
        obj["name"] = s.name
    if s.version:
        obj["version"] = s.version
    _put_attributes(obj, s.attributes, s.dropped_attributes_count)
    return obj


def _span(s: Span) -> JsonObject:
    obj: JsonObject = {
        "traceId": _id(s.trace_id, 16, "traceId"),
        "spanId": _id(s.span_id, 8, "spanId"),
    }
    if s.trace_state:
        obj["traceState"] = s.trace_state
    if s.parent_span_id:
        obj["parentSpanId"] = _id(s.parent_span_id, 8, "parentSpanId")
    obj["name"] = s.name
    obj["kind"] = int(s.kind)
    obj["startTimeUnixNano"] = _fixed64(s.start_time_unix_nano)
    obj["endTimeUnixNano"] = _fixed64(s.end_time_unix_nano)
    _put_attributes(obj, s.attributes, s.dropped_attributes_count)
    if s.events:
        obj["events"] = [_event(e) for e in s.events]
    if s.dropped_events_count:
        obj["droppedEventsCount"] = _u32(s.dropped_events_count, "droppedEventsCount")
    if s.links:
        obj["links"] = [_link(link) for link in s.links]
    if s.dropped_links_count:
        obj["droppedLinksCount"] = _u32(s.dropped_links_count, "droppedLinksCount")
    status = _status(s.status)
    if status:
        obj["status"] = status
    if s.flags:
        obj["flags"] = _u32(s.flags, "flags")
    return obj


def _event(e: Event) -> JsonObject:
    obj: JsonObject = {}
    if e.time_unix_nano:
        obj["timeUnixNano"] = _fixed64(e.time_unix_nano)
    if e.name:
        obj["name"] = e.name
    _put_attributes(obj, e.attributes, e.dropped_attributes_count)
    return obj


def _link(link: Link) -> JsonObject:
    obj: JsonObject = {
        "traceId": _id(link.trace_id, 16, "traceId"),
        "spanId": _id(link.span_id, 8, "spanId"),
    }
    if link.trace_state:
        obj["traceState"] = link.trace_state
    _put_attributes(obj, link.attributes, link.dropped_attributes_count)
    if link.flags:
        obj["flags"] = _u32(link.flags, "flags")
    return obj


def _status(s: Status) -> JsonObject:
    obj: JsonObject = {}
    if s.message:
        obj["message"] = s.message
    if s.code != StatusCode.UNSET:
        obj["code"] = int(s.code)
    return obj


# --- Attributes and values --------------------------------------------------------


def _put_attributes(obj: JsonObject, attributes: Attributes, dropped: int) -> None:
    if attributes:
        obj["attributes"] = _key_values(attributes)
    if dropped:
        obj["droppedAttributesCount"] = _u32(dropped, "droppedAttributesCount")


def _key_values(attributes: Attributes) -> list[JsonObject]:
    return [{"key": kv.key, "value": _any_value(kv.value)} for kv in attributes]


def _any_value(v: Value) -> JsonObject:
    # bool before int: bool is a subclass of int.
    if v is None:
        return {}
    if isinstance(v, str):
        return {"stringValue": v}
    if isinstance(v, bool):
        return {"boolValue": v}
    if isinstance(v, int):
        if not _INT64_MIN <= v <= _INT64_MAX:
            raise ValueError(f"intValue {v} is outside the 64-bit signed range")
        return {"intValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": _double(v)}
    if isinstance(v, tuple):
        return {"arrayValue": {"values": [_any_value(x) for x in v]} if v else {}}
    if isinstance(v, KvList):
        return {"kvlistValue": {"values": _key_values(v.values)} if v.values else {}}
    if isinstance(v, bytes):
        return {"bytesValue": base64.b64encode(v).decode("ascii")}
    raise TypeError(f"unsupported attribute value type: {type(v).__name__}")


def _double(v: float) -> float | str:
    if math.isnan(v):
        return "NaN"
    if math.isinf(v):
        return "Infinity" if v > 0 else "-Infinity"
    return v


def _id(v: str, n_bytes: int, field: str) -> str:
    if len(v) != 2 * n_bytes or not _HEX.fullmatch(v) or v.strip("0") == "":
        raise ValueError(f"{field} must be {2 * n_bytes} lower-case hex characters, not all zero")
    return v


def _u32(v: int, field: str) -> int:
    if not 0 <= v < 2**32:
        raise ValueError(f"{field} {v} is outside the unsigned 32-bit range")
    return v


def _fixed64(v: int) -> str:
    if not 0 <= v < 2**64:
        raise ValueError(f"timestamp {v} is outside the unsigned 64-bit range")
    return str(v)


def _bad_string_path(node: object, path: str) -> str:
    """Path of the first string in ``node`` that cannot be encoded as UTF-8."""
    if isinstance(node, str):
        try:
            node.encode("utf-8")
        except UnicodeEncodeError:
            return path
        return ""
    if isinstance(node, dict):
        # Keys are the writer's own field names, so only values can be bad.
        for k, v in node.items():
            found = _bad_string_path(v, f"{path}.{k}".lstrip("."))
            if found:
                return found
    if isinstance(node, list):
        for i, v in enumerate(node):
            found = _bad_string_path(v, f"{path}[{i}]")
            if found:
                return found
    return ""
