"""Pinned OpenTelemetry convention versions and every name eagain reads or writes.

This is the only place OpenTelemetry and ``eagain.*`` names are spelled out
(Spec 001 section 5, plan section 2). Other modules use these constants, and
``normalise.py`` is the only module that reads ``gen_ai.*`` attributes, so moving
to newer conventions touches this file and the normaliser only.

Pins
----
- ``open-telemetry/semantic-conventions-genai`` at commit
  ``9d1e748280e64cf5688d7f348bf86be24c3fce12`` (2026-11-02). It has no tagged
  release yet. Every ``gen_ai.*`` name is at ``development`` stability.
- ``open-telemetry/semantic-conventions`` at ``v1.45.0``, for ``vcs.*``
  (``release_candidate``), plus ``error.type``, ``exception.*`` and the
  ``exception`` event (all ``stable``).

How the names were checked
--------------------------
Checked once by hand on 2026-11-03, by reading the model files at the pins:

- ``model/gen-ai/registry.yaml``: one ``key:`` entry for each ``gen_ai.*``
  attribute below. The operation names ``chat``, ``invoke_agent`` and
  ``execute_tool`` are members of ``gen_ai.operation.name``.
- ``model/gen-ai/events.yaml``: ``gen_ai.client.inference.operation.details``,
  and ``gen_ai.client.operation.exception``, which carries ``exception.type``
  and ``exception.message``.
- ``model/gen-ai/spans.yaml``: ``gen_ai.input.messages`` and
  ``gen_ai.output.messages`` on inference spans, the ``gen_ai.tool.call.*``
  attributes on ``execute_tool``, and ``gen_ai.skill.name`` in its span name.
- ``model/gen-ai/gen-ai-output-messages.json``: the ``reasoning`` part type.
- At v1.45.0: ``model/vcs/registry.yaml``, ``model/error/registry.yaml``,
  ``model/exceptions/registry.yaml`` and ``model/exceptions/events.yaml``.

Unit tests stay offline. They check these constants against Spec 001's tables.
Moving either pin means repeating this check and updating the dates above.
"""

from __future__ import annotations

from typing import Final

GENAI_CONVENTIONS: Final = "open-telemetry/semantic-conventions-genai"
GENAI_CONVENTIONS_COMMIT: Final = "9d1e748280e64cf5688d7f348bf86be24c3fce12"
CORE_CONVENTIONS: Final = "open-telemetry/semantic-conventions"
CORE_CONVENTIONS_VERSION: Final = "v1.45.0"

PINNED_VERSIONS: Final[dict[str, str]] = {
    GENAI_CONVENTIONS: GENAI_CONVENTIONS_COMMIT,
    CORE_CONVENTIONS: CORE_CONVENTIONS_VERSION,
}
"""What every report records as the conventions it was built against."""

# --- Operations (values of gen_ai.operation.name) ---------------------------

OP_INVOKE_AGENT: Final = "invoke_agent"
OP_CHAT: Final = "chat"
OP_EXECUTE_TOOL: Final = "execute_tool"

# --- GenAI attributes ---------------------------------------------------------

GEN_AI_OPERATION_NAME: Final = "gen_ai.operation.name"
GEN_AI_CONVERSATION_ID: Final = "gen_ai.conversation.id"
GEN_AI_CONVERSATION_COMPACTED: Final = "gen_ai.conversation.compacted"
GEN_AI_PROVIDER_NAME: Final = "gen_ai.provider.name"
GEN_AI_AGENT_NAME: Final = "gen_ai.agent.name"
GEN_AI_AGENT_ID: Final = "gen_ai.agent.id"
GEN_AI_AGENT_VERSION: Final = "gen_ai.agent.version"
GEN_AI_REQUEST_MODEL: Final = "gen_ai.request.model"
GEN_AI_USAGE_INPUT_TOKENS: Final = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS: Final = "gen_ai.usage.output_tokens"
GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS: Final = "gen_ai.usage.cache_read.input_tokens"
GEN_AI_USAGE_CACHE_WRITE_INPUT_TOKENS: Final = "gen_ai.usage.cache_write.input_tokens"
GEN_AI_TOOL_NAME: Final = "gen_ai.tool.name"
GEN_AI_TOOL_CALL_ID: Final = "gen_ai.tool.call.id"
GEN_AI_TOOL_CALL_ARGUMENTS: Final = "gen_ai.tool.call.arguments"
"""Opt-in in the conventions, so third-party traces may omit it."""
GEN_AI_TOOL_CALL_RESULT: Final = "gen_ai.tool.call.result"
"""Opt-in in the conventions, so third-party traces may omit it."""
GEN_AI_SKILL_NAME: Final = "gen_ai.skill.name"
GEN_AI_INPUT_MESSAGES: Final = "gen_ai.input.messages"
GEN_AI_OUTPUT_MESSAGES: Final = "gen_ai.output.messages"

# --- GenAI events and message parts --------------------------------------------

EVENT_INFERENCE_DETAILS: Final = "gen_ai.client.inference.operation.details"
EVENT_GEN_AI_EXCEPTION: Final = "gen_ai.client.operation.exception"
PART_REASONING: Final = "reasoning"
"""``type`` of a reasoning message part in input and output messages."""

# --- Core conventions (v1.45.0) -----------------------------------------------

VCS_REPOSITORY_URL_FULL: Final = "vcs.repository.url.full"
VCS_REF_HEAD_NAME: Final = "vcs.ref.head.name"
VCS_REF_HEAD_REVISION: Final = "vcs.ref.head.revision"
ERROR_TYPE: Final = "error.type"
EVENT_EXCEPTION: Final = "exception"
EXCEPTION_TYPE: Final = "exception.type"
EXCEPTION_MESSAGE: Final = "exception.message"

# --- eagain extensions (Spec 001 section 5, "Extensions") ----------------------

EAGAIN_TOOL_OUTCOME: Final = "eagain.tool.outcome"
OUTCOME_OK: Final = "ok"
OUTCOME_ERROR: Final = "error"
OUTCOME_DENIED: Final = "denied"
OUTCOME_UNKNOWN: Final = "unknown"
TOOL_OUTCOMES: Final = (OUTCOME_OK, OUTCOME_ERROR, OUTCOME_DENIED, OUTCOME_UNKNOWN)

EVENT_EAGAIN_INTERRUPT: Final = "eagain.interrupt"
EVENT_EAGAIN_COMPACTION: Final = "eagain.compaction"
EAGAIN_SOURCE_PREFIX: Final = "eagain.source."
"""Prefix of the ``eagain.source.*`` attributes that point back to the source record."""
EAGAIN_PROJECT_ID: Final = "eagain.project.id"
EAGAIN_PROJECT_ID_SOURCE: Final = "eagain.project.id_source"
EAGAIN_CWD: Final = "eagain.cwd"
EAGAIN_TURN_ID: Final = "eagain.turn.id"
EAGAIN_SKILL: Final = "eagain.skill"

# --- Name sets ----------------------------------------------------------------

OPERATIONS: Final = frozenset({OP_INVOKE_AGENT, OP_CHAT, OP_EXECUTE_TOOL})

GENAI_NAMES: Final = frozenset(
    {
        GEN_AI_OPERATION_NAME,
        GEN_AI_CONVERSATION_ID,
        GEN_AI_CONVERSATION_COMPACTED,
        GEN_AI_PROVIDER_NAME,
        GEN_AI_AGENT_NAME,
        GEN_AI_AGENT_ID,
        GEN_AI_AGENT_VERSION,
        GEN_AI_REQUEST_MODEL,
        GEN_AI_USAGE_INPUT_TOKENS,
        GEN_AI_USAGE_OUTPUT_TOKENS,
        GEN_AI_USAGE_CACHE_READ_INPUT_TOKENS,
        GEN_AI_USAGE_CACHE_WRITE_INPUT_TOKENS,
        GEN_AI_TOOL_NAME,
        GEN_AI_TOOL_CALL_ID,
        GEN_AI_TOOL_CALL_ARGUMENTS,
        GEN_AI_TOOL_CALL_RESULT,
        GEN_AI_SKILL_NAME,
        GEN_AI_INPUT_MESSAGES,
        GEN_AI_OUTPUT_MESSAGES,
        EVENT_INFERENCE_DETAILS,
        EVENT_GEN_AI_EXCEPTION,
    }
)
"""Names from the pinned ``semantic-conventions-genai`` commit."""

CORE_NAMES: Final = frozenset(
    {
        VCS_REPOSITORY_URL_FULL,
        VCS_REF_HEAD_NAME,
        VCS_REF_HEAD_REVISION,
        ERROR_TYPE,
        EVENT_EXCEPTION,
        EXCEPTION_TYPE,
        EXCEPTION_MESSAGE,
    }
)
"""Names from ``semantic-conventions`` v1.45.0."""

EXTENSION_NAMES: Final = frozenset(
    {
        EAGAIN_TOOL_OUTCOME,
        EVENT_EAGAIN_INTERRUPT,
        EVENT_EAGAIN_COMPACTION,
        EAGAIN_PROJECT_ID,
        EAGAIN_PROJECT_ID_SOURCE,
        EAGAIN_CWD,
        EAGAIN_TURN_ID,
        EAGAIN_SKILL,
    }
)
"""eagain's own names. ``eagain.source.*`` is matched by ``EAGAIN_SOURCE_PREFIX``."""


def is_extension(name: str) -> bool:
    return name in EXTENSION_NAMES or name.startswith(EAGAIN_SOURCE_PREFIX)
