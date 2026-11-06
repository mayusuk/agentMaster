"""In-memory form of OTLP trace data, as read from and written to OTLP JSON Lines.

The classes mirror the OTLP protobuf messages (``TracesData`` down to ``Span``)
and keep their field order. Attribute values are plain Python values:

========================  ======================================
OTLP ``AnyValue`` field   Python value
========================  ======================================
``stringValue``           ``str``
``boolValue``             ``bool``
``intValue``              ``int`` (64-bit signed range)
``doubleValue``           ``float``
``bytesValue``            ``bytes``
``arrayValue``            ``tuple`` of values
``kvlistValue``           :class:`KvList`
(empty ``AnyValue``)      ``None``
========================  ======================================

Attributes are ordered tuples of :class:`KeyValue`, so order and any duplicate
keys survive a read followed by a write. IDs are lower-case hex strings, and an
empty string means "not set" (for example ``parent_span_id`` on a root span).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import NamedTuple, TypeAlias


@dataclass(frozen=True, slots=True)
class KvList:
    """A ``kvlistValue``: an ordered list of key-value pairs."""

    values: tuple[KeyValue, ...] = ()


Value: TypeAlias = "str | bool | int | float | bytes | tuple[Value, ...] | KvList | None"


class KeyValue(NamedTuple):
    key: str
    value: Value


Attributes: TypeAlias = tuple[KeyValue, ...]


class SpanKind(IntEnum):
    UNSPECIFIED = 0
    INTERNAL = 1
    SERVER = 2
    CLIENT = 3
    PRODUCER = 4
    CONSUMER = 5


class StatusCode(IntEnum):
    UNSET = 0
    OK = 1
    ERROR = 2


@dataclass(frozen=True, slots=True)
class Status:
    message: str = ""
    code: StatusCode = StatusCode.UNSET


@dataclass(frozen=True, slots=True)
class Event:
    time_unix_nano: int = 0
    name: str = ""
    attributes: Attributes = ()
    dropped_attributes_count: int = 0


@dataclass(frozen=True, slots=True)
class Link:
    trace_id: str
    span_id: str
    trace_state: str = ""
    attributes: Attributes = ()
    dropped_attributes_count: int = 0
    flags: int = 0


@dataclass(frozen=True, slots=True)
class Span:
    trace_id: str
    span_id: str
    name: str = ""
    trace_state: str = ""
    parent_span_id: str = ""
    flags: int = 0
    kind: SpanKind = SpanKind.UNSPECIFIED
    start_time_unix_nano: int = 0
    end_time_unix_nano: int = 0
    attributes: Attributes = ()
    dropped_attributes_count: int = 0
    events: tuple[Event, ...] = ()
    dropped_events_count: int = 0
    links: tuple[Link, ...] = ()
    dropped_links_count: int = 0
    status: Status = Status()


@dataclass(frozen=True, slots=True)
class InstrumentationScope:
    name: str = ""
    version: str = ""
    attributes: Attributes = ()
    dropped_attributes_count: int = 0


@dataclass(frozen=True, slots=True)
class Resource:
    attributes: Attributes = ()
    dropped_attributes_count: int = 0


@dataclass(frozen=True, slots=True)
class ScopeSpans:
    scope: InstrumentationScope = InstrumentationScope()
    spans: tuple[Span, ...] = ()
    schema_url: str = ""


@dataclass(frozen=True, slots=True)
class ResourceSpans:
    resource: Resource = Resource()
    scope_spans: tuple[ScopeSpans, ...] = ()
    schema_url: str = ""


@dataclass(frozen=True, slots=True)
class TracesData:
    """One line of an OTLP JSON Lines traces file."""

    resource_spans: tuple[ResourceSpans, ...] = ()

    def spans(self) -> tuple[tuple[Resource, InstrumentationScope, Span], ...]:
        """Every span on this line, with the resource and scope it belongs to."""
        return tuple(
            (rs.resource, ss.scope, span)
            for rs in self.resource_spans
            for ss in rs.scope_spans
            for span in ss.spans
        )
