# Work plan: semconv module with pinned versions

**Issue:** [#6](https://github.com/mayusuk/agentMaster/issues/6) (feature)
**Branch:** `issue/6-semconv-module-with-pinned-versions`
**Base:** `origin/main @ 7f79edb` (checked before branching)
**Status:** Draft

## Summary

Adds `src/eagain/semconv.py`, which holds the pinned OpenTelemetry convention versions and one constant for every operation, attribute, event and message-part name in Spec 001 section 5, including the `eagain.*` extensions. Each convention name was checked against the pinned sources. Later modules (the normaliser, importers, the OTLP writer) refer to names only through these constants, so moving to new convention versions touches one file.

## Context

- Spec 001 section 5 (Mapping and Extensions tables, outcome and error-text orders). Plan section 2 lists `semconv.py` as "pinned versions and every attribute name". Plan task M1.3 (`docs/plans/2026-11-03-v0-1-m1-format.md`, T4).
- The pins are `open-telemetry/semantic-conventions-genai` commit `9d1e748` (full SHA `9d1e748280e64cf5688d7f348bf86be24c3fce12`, committed 2026-11-02, with no tagged release) and `open-telemetry/semantic-conventions` v1.45.0 for `vcs.*`, `error.type` and `exception.*`.
- CLAUDE.md: rules read the internal model, never OTel names, and `normalise.py` is the only reader of `gen_ai.*`. This module is where those names live. It has no logic and imports nothing from eagain.

## Approach

- Use plain `Final[str]` constants grouped by kind: operations, attributes, events, message parts, and extensions.
- `PINNED_VERSIONS` maps each conventions repository to its pin, for reports to record (Spec 001 section 5: "records it in every report").
- Frozensets `GENAI_NAMES`, `CORE_NAMES` and `EXTENSION_NAMES` let tests and the future normaliser check membership. `EAGAIN_SOURCE_PREFIX` covers the open-ended `eagain.source.*` family.
- The `eagain.tool.outcome` values (`ok`, `error`, `denied`, `unknown`) are constants here too, because they are wire values.
- The docstring records how the names were checked. The check was done once by hand, by reading `model/gen-ai/registry.yaml`, `events.yaml`, `spans.yaml` and `gen-ai-output-messages.json` at the pinned commit, and `model/vcs/registry.yaml`, `model/error/registry.yaml`, `model/exceptions/registry.yaml` and `events.yaml` at v1.45.0. Tests stay offline and check the constants against the spec's tables, which are kept as a list in the test.

## Steps

- [x] `semconv.py` with pinned versions and every name, plus tests that every section 5 name has a constant, that extensions use the `eagain.` prefix, and that the module imports nothing from eagain.
- [ ] Outcome, verify, ship.

## Acceptance criteria

- Every name in Spec 001 section 5's Mapping and Extensions tables has a constant, and a test checks this against a list kept in the test.
- The pinned versions are importable for reports to record.

## Verification

Standard checks. Checking against the upstream sources is a one-off manual step recorded in the module docstring. Tests make no network calls.

## Risks and open questions

- Stability at the pins: the GenAI names are `development`. `vcs.*` is `release_candidate`. `error.type`, `exception.type`, `exception.message` and the `exception` event are `stable`. Moving the GenAI pin means repeating the check.
- `gen_ai.conversation.compacted`: the conventions say instrumentations SHOULD NOT set it to `false`. The normaliser should treat it as absent-or-true, which matches Spec 001's "`= true` on later model calls".

## Outcome

_Filled in before shipping._
