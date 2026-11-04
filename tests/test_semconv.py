"""semconv: pinned versions and every Spec 001 section 5 name."""

from __future__ import annotations

import ast
from pathlib import Path

from eagain import semconv

# Every name in Spec 001 section 5, copied from its Mapping and Extensions tables
# and the outcome and error-text sections. Kept here on purpose: if a constant is
# renamed or dropped, this list fails rather than silently following it.
SPEC_MAPPING = {
    # Operations
    "invoke_agent",
    "chat",
    "execute_tool",
    # Session, agent identity
    "gen_ai.operation.name",
    "gen_ai.conversation.id",
    "gen_ai.provider.name",
    "gen_ai.agent.name",
    "gen_ai.agent.id",
    "gen_ai.agent.version",
    # Model call
    "gen_ai.request.model",
    "gen_ai.usage.input_tokens",
    "gen_ai.usage.output_tokens",
    "gen_ai.usage.cache_read.input_tokens",
    "gen_ai.usage.cache_write.input_tokens",
    # Repository
    "vcs.repository.url.full",
    "vcs.ref.head.name",
    "vcs.ref.head.revision",
    # Tool call, skill load
    "gen_ai.tool.name",
    "gen_ai.tool.call.id",
    "gen_ai.tool.call.arguments",
    "gen_ai.tool.call.result",
    "gen_ai.skill.name",
    # Failure
    "error.type",
    "gen_ai.client.operation.exception",
    "exception",
    "exception.message",
    # Compaction
    "gen_ai.conversation.compacted",
    # Message and reasoning content
    "gen_ai.client.inference.operation.details",
    "gen_ai.input.messages",
    "gen_ai.output.messages",
    "reasoning",
}

SPEC_EXTENSIONS = {
    "eagain.tool.outcome",
    "eagain.interrupt",
    "eagain.compaction",
    "eagain.project.id",
    "eagain.project.id_source",
    "eagain.cwd",
    "eagain.turn.id",
    "eagain.skill",
}


def _constant_values() -> set[str]:
    return {v for k, v in vars(semconv).items() if k.isupper() and isinstance(v, str)}


def test_every_section_5_name_has_a_constant() -> None:
    values = _constant_values()
    missing = sorted((SPEC_MAPPING | SPEC_EXTENSIONS) - values)
    assert missing == []
    assert semconv.EAGAIN_SOURCE_PREFIX == "eagain.source."


def test_name_sets_partition_the_attribute_and_event_names() -> None:
    sets = [semconv.GENAI_NAMES, semconv.CORE_NAMES, semconv.EXTENSION_NAMES]
    union = frozenset().union(*sets)
    assert sum(len(s) for s in sets) == len(union)
    assert union | semconv.OPERATIONS | {semconv.PART_REASONING} >= SPEC_MAPPING | SPEC_EXTENSIONS
    assert all(n.startswith("gen_ai.") for n in semconv.GENAI_NAMES)
    assert all(n.startswith("eagain.") for n in semconv.EXTENSION_NAMES)
    assert not any(n.startswith(("gen_ai.", "eagain.")) for n in semconv.CORE_NAMES)


def test_extensions_are_recognised_including_source_pointers() -> None:
    assert semconv.is_extension("eagain.cwd")
    assert semconv.is_extension("eagain.source.record_uuid")
    assert not semconv.is_extension("gen_ai.tool.name")
    assert not semconv.is_extension("eagain.unknown")


def test_tool_outcomes_match_spec() -> None:
    assert semconv.TOOL_OUTCOMES == ("ok", "error", "denied", "unknown")


def test_pinned_versions_are_importable_for_reports() -> None:
    assert semconv.PINNED_VERSIONS == {
        "open-telemetry/semantic-conventions-genai": "9d1e748280e64cf5688d7f348bf86be24c3fce12",
        "open-telemetry/semantic-conventions": "v1.45.0",
    }
    assert semconv.GENAI_CONVENTIONS_COMMIT.startswith("9d1e748")


def test_semconv_imports_nothing_from_eagain() -> None:
    tree = ast.parse(Path(semconv.__file__).read_text(encoding="utf-8"))
    imported = {
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    } | {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    assert not any(m == "eagain" or m.startswith("eagain.") for m in imported)
