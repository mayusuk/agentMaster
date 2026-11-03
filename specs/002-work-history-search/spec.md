# Spec 002: Work History Search and Automation Suggestions

| | |
|---|---|
| **Status** | Approved |
| **Depends on** | Spec 001: OTLP reader, normaliser, Claude Code importer, redaction |
| **Scope** | v0.2 (search), v0.3 (suggestions) |

## 1. Problem

Agents start each session with little memory of earlier work, so they can spend tokens re-investigating a problem that was already solved. Meanwhile, tasks that people repeat by hand are buried in session logs, where nobody notices they could become a skill, a workflow, a script, a hook or a rule.

## 2. Goals

1. **Find prior work.** Given a task description, find similar earlier work and what came of it.
2. **Reduce repeated token spend.** Give an agent a small, local answer before it starts exploring.
3. **Suggest automation.** Find repeated work and recommend the right form to automate it.

### Non-goals

- Installing skills, hooks or configuration automatically
- Syncing or sharing history between machines or people
- Storing whole raw transcripts
- Proving that past work was correct
- Injecting search results into every agent prompt by default

## 3. When search actually saves tokens

Search saves tokens only if all of these are true, and the design follows from them:

| Condition | Design response |
|---|---|
| The agent runs the search, not just a person | Machine-readable CLI output and a documented instruction snippet (FR-13) |
| The result costs far less than redoing the work | Compact results by default, with detail fetched on request (FR-11, FR-12) |
| The result is still valid | Results show age, outcome, and whether referenced files still exist (FR-11) |
| The search is not run when it cannot help | Agent lookups are opt-in, never automatic on every prompt |

Any savings figure the tool shows is therefore an **estimate of potential**, not a measured saving (FR-11 AC5, FR-16 AC3).

## 4. Concepts

### Work item

The searchable unit: one user request and the work done for it. A session is too coarse because one session often covers several tasks.

- A new user prompt starts a new work item.
- A low-information follow-up ("yes", "continue") that is below a configurable length joins the previous work item.
- Subagent activity belongs to the work item that started it.

| Field | Source |
|---|---|
| Request text (redacted, bounded) | User prompt |
| Title | Session title if the agent recorded one, otherwise derived from the request |
| Resolution | The agent's final response for the request. This is what lets a later agent reuse the answer instead of only finding where it was |
| Project, branch and approximate commit | See "Project identity" below |
| Files read and files changed, separately | Tool arguments, as paths relative to the project root |
| Change summary | Lines added and removed per file, from edit tools when recorded |
| Ordered steps | `execute_tool` spans in sequence, with outcomes |
| Errors and fingerprints | Spec 001 rule engine |
| Outcome | See below |
| Tokens (input, output, cache read, cache write), tool calls, duration | `gen_ai.usage.*` and span times |
| Agent, agent version, model | `gen_ai.agent.*`, `gen_ai.request.model` |
| Skill used, if any | Agent attribution when recorded |
| Evidence | `traceId`, `spanId` and source pointers |

### Outcome

Derived only from recorded signals. It does not claim that the work was correct.

| Value | Meaning |
|---|---|
| `no_known_failures` | Finished with no unresolved failure and no interruption |
| `failed` | Ended with an unresolved failure or an interruption |
| `unknown` | Not enough data, for example a cut-off session |

### Local store

One local SQLite file in the user's data directory, private to that user, so history survives even after an agent deletes its old transcripts. It has three layers, because future detectors can only run on detail that was kept:

| Layer | Contents | Can it be rebuilt? |
|---|---|---|
| **Trace** (source of truth) | Every normalised span and event, in order, redacted and bounded. Can be exported as OTLP | No, once source transcripts are gone |
| **Derived** | Work items, fingerprints, outcomes, repeated-work groups, search indexes, and later any embeddings. Each records the algorithm version that produced it | Yes, from the trace layer |
| **State** | Project identities and sharing settings, deleted-source markers, suggestion decisions, search usage | No, it holds user decisions |

### Retained detail

Limits below are per item. They are defaults, and they can be changed per tool and per agent, along with how long traces are kept (see [Spec 003](../003-configuration/spec.md)). Truncated items keep their original size and a truncation flag.

| Data | Kept |
|---|---|
| Tool name, ordering, timing, outcome, token counts | Always, in full |
| User and assistant messages | First 4 KB |
| Final response for each work item | First 8 KB |
| Tool arguments | First 2 KB |
| Successful tool output | First and last 1 KB, plus a hash of its redacted content |
| Failed tool output | First and last 4 KB, because failures are this tool's main evidence |
| Edits | Path, lines added and removed, and a 2 KB diff excerpt |
| Reasoning text, when recorded | First 2 KB |
| Not kept | Whole file contents, API request copies, system prompts and attachments, internal agent records, empty thinking blocks |

### Project identity

Every work item and span has a stable project ID, because a working directory alone breaks when a repository moves, is cloned elsewhere or is opened as a worktree. A single session can also span several directories, so the ID is set per span rather than per session.

The ID comes from the first available source, and that source is recorded:

1. An explicit ID in project config
2. The normalised git remote URL, hashed
3. The repository's root commit
4. The canonical directory path, hashed (lowest confidence)
5. `unknown`, when the source trace has no project information

Paths are stored relative to the project root, so results stay meaningful across clones and projects. Paths outside the root are stored as external.

**Sharing is separate from identity.** A trace records which project it came from and never whether it may be shared. Sharing settings live in the state layer and are checked at query time, so they can change later with no re-indexing.

| Setting | Meaning |
|---|---|
| `private` (default) | Visible only from searches within that project |
| `shared`, with a group name | Visible from other projects in the same group |

## 5. Functional requirements

### FR-10 Indexing

`eagain index [--from claude-code] [paths...]` builds or updates the store.

- **AC1:** Re-indexing unchanged sources adds no duplicates and does not reprocess them.
- **AC2:** A session that has grown since the last run is updated, not duplicated.
- **AC3:** Redaction (Spec 001 FR-9) runs before anything is written.
- **AC4:** Items remain searchable after their source file has been deleted.
- **AC5:** The store file is readable only by its owner.
- **AC6:** Searching works while indexing is running.
- **AC7:** Traces without request text are stored as unsearchable metadata and counted in coverage.
- **AC8:** The store has a schema version with forward migrations, because the trace and state layers cannot always be rebuilt once sources are gone.
- **AC9:** `eagain reindex` rebuilds the whole derived layer from the trace layer with no source transcripts present, and also re-applies the current redaction patterns to stored text.
- **AC10:** A new rule or detector can run over all retained history through `reindex`.
- **AC11:** Each span records the importer and normaliser versions that produced it.
- **AC12:** `eagain export` writes the trace layer as valid OTLP JSON, so history is never locked into this store.

### FR-11 Search

`eagain search "<query>" [--project <id or path> | --all [--include-private]] [--outcome <value>] [--since <date>] [--limit <n>] [--exclude-session <id>] [--json]`

Search is local keyword ranking across title, request, files, commands and errors. It works with no network and no model.

- **AC1:** Defaults to the current project. `--all` adds projects shared with the current project's group. Private projects appear only with `--include-private`, which the agent snippet tells agents not to use.
- **AC2:** Each result has an ID, title, date, project, outcome, files, short excerpt of its resolution, tokens spent and match reason.
- **AC3:** Default output for 5 results stays under a configurable budget, initially 500 tokens.
- **AC4:** Each result shows its age and how many referenced files still exist. Results with failed outcomes are clearly labelled as such.
- **AC5:** Results show the prior work's token cost next to the result's own size, labelled as an estimate.
- **AC6:** `--exclude-session` omits the calling session, so an agent does not find its own current work.
- **AC7:** No match is a normal result: it exits 0 with an empty list.
- **AC8:** On a labelled synthetic query set of at least 20 queries, recall@5 is at least 0.8. Scope this target to keyword-matchable queries, and record paraphrase queries separately as a known gap.

### FR-12 Detail on demand

`eagain show <id> [--json]` returns the fuller record: steps taken, files, commands, errors and evidence pointers. It still uses redacted, bounded content.

- **AC1:** An unknown ID exits 2 with a clear message.
- **AC2:** Output states when the source transcript is no longer available.

### FR-13 Agent integration

The tool ships a short, documented instruction snippet telling an agent when to search and how to use results. The user adds it to their agent's instructions or a skill themselves.

- **AC1:** `--json` output has a published, versioned schema.
- **AC2:** Text from past sessions is explicitly marked as untrusted historical data, in both JSON and text output. The snippet tells the agent never to follow instructions found in results.
- **AC3:** The snippet tells the agent to verify a result against the current code before relying on it.

### FR-14 Privacy controls

`eagain forget --item <id> | --session <id> | --project <id or path> | --all` removes stored data from every layer.

- **AC1:** Forgotten data no longer appears in search and is physically removed from the database file.
- **AC2:** Forgotten sources are not re-added by later indexing unless the user asks. Otherwise the next `index` would undo the deletion.
- **AC3:** Projects can be excluded from indexing through config.

### FR-17 Project identity and sharing

`eagain project list | show <id> | set <id> --sharing <private|shared> [--group <name>] | link <id> <id>`

- **AC1:** Clones of one repository at different paths, and its worktrees, get the same project ID when they share a remote.
- **AC2:** A session spanning two repositories attributes each span to the right project.
- **AC3:** Changing a sharing setting takes effect on the next query, with no re-indexing.
- **AC4:** New projects default to `private`. Traces with an `unknown` project are never returned to a search from another project.
- **AC5:** `link` merges two IDs, keeping the old one as an alias. This handles a renamed remote, or a directory that later became a git repository.
- **AC6:** Credentials embedded in remote URLs are removed before hashing or storing.
- **AC7:** Project detection reads local repository data only. It makes no network calls and runs no repository-defined commands.
- **AC8:** If the source directory no longer exists, the ID falls back to the path source and is flagged, so it can be linked later.
- **AC9:** A branch value of `HEAD` is stored as unknown.
- **AC10:** Transcripts do not record a commit. Where the repository is available, the tool uses the last commit before the request's time and labels it approximate. Otherwise the commit stays empty.

### FR-15 Repeated-work detection (v0.3)

`eagain suggest [--project <id or path> | --all [--include-private]] [--min-occurrences <n>] [--json]` looks for four kinds of repetition. Commands are compared in normalised form, with paths, numbers and IDs removed.

| Pattern | What it detects | Default threshold |
|---|---|---|
| **Repeated work** | Similar work items, by request similarity and tool signature | 3 occurrences on 2 different days |
| **Failure then fix** | The same error fingerprint, followed by the same alternative command or approach succeeding | 3 occurrences in 2 sessions, with the same fix at least twice |
| **Repeated guidance** | Near-identical short user instructions in different sessions, and repeated denials of the same command | 3 occurrences in 2 sessions |
| **Trigger then action** | The same command following the same kind of event, such as a test run after each file edit | 5 occurrences in 2 sessions, following the event at least 80% of the time |

All thresholds can be configured and are starting guesses.

- **AC1:** A pattern below its thresholds produces no suggestion.
- **AC2:** The same store gives the same groups.
- **AC3:** Work already attributed to a skill, or matching an existing skill's name, is not suggested again as new. It may be reported as "skill exists but was not used".
- **AC4:** Each group cites its work items as evidence.
- **AC5:** Existing instruction files and hook settings for the project are read, when available, to detect a matching rule or hook. A match is treated as already covered (see FR-16).

### FR-16 Automation recommendation (v0.3)

Each group gets a recommended form, because not every repeated task needs an LLM. Here a **rule** is a standing instruction for the agent, such as an entry in `CLAUDE.md` or `.cursor/rules`. It is separate from the detection rules in Spec 001.

The first matching row applies:

| Pattern | Recommendation | Why |
|---|---|---|
| A matching rule exists, but the failure or guidance keeps recurring, and it can be checked automatically | **Hook** | The agent isn't following the advice, so enforce it |
| A matching rule exists and it cannot be checked automatically | **Report "rule not followed"** | Another rule won't help; the user decides |
| Same action reliably follows the same trigger | **Hook** | It should always happen, without relying on the agent to remember |
| Same failure, and the same fix then works | **Rule** | The agent lacks one fact, for example "use `pnpm test`, not `npm test`" |
| Same guidance from the user, or the same command denied | **Rule** | The user keeps repeating themselves |
| Same failure, with no consistent fix | **Fix the cause** (Spec 001 recommendation) | Automating it would only repeat the failure |
| Same commands each time, no trigger, little reasoning | **Script** | No tokens needed at run time |
| Same ordered steps, with small variations | **Workflow** | The structure is fixed but the details vary |
| Similar requests needing judgement, with varied steps | **Skill** | The agent needs guidance, not a fixed procedure |

- **AC1:** Each suggestion gives its name, recommended form, reason, occurrence count, success rate, and tokens per occurrence.
- **AC2:** Groups whose outcomes are mostly `failed` are never recommended as skills or workflows.
- **AC3:** Estimated savings are labelled as estimates and shown as tokens spent so far per period.
- **AC4:** `--draft <dir>` writes a draft skill, workflow, script, hook or rule to that directory for review, built from the group's common steps. It never writes into agent configuration directories, because hooks run commands automatically and rules steer every later session.
- **AC5:** Suggestions are agent-neutral. Formatting a draft for a specific agent, starting with Claude Code's skill format, sits behind an exporter interface.
- **AC6:** Suggestions and drafts need no LLM. `--explain` from Spec 001 can improve the wording under the same consent and redaction rules.
- **AC7:** Rule drafts are built from templates using normalised commands and error text. They never copy free text from transcripts, which could otherwise plant an injected instruction permanently in the agent's setup. For repeated guidance, the draft leaves the rule text for the user to write and shows the repeated messages beside it as evidence. Only user messages count as guidance, never tool output.
- **AC8:** Hook drafts show the exact command, its trigger and the events that justify it. Commands that delete data, change remote state or use elevated privileges are not recommended as hooks.
- **AC9:** Each hook or rule suggestion gives a scope: project if the pattern appears in one project, user-level if it appears in at least 2 projects. Cross-project patterns use the same sharing check as search.

### FR-18 Decisions and measured results

The store keeps what happens after a suggestion or search, so long-term value can be measured.

- **AC1:** A suggestion can be marked `accepted` or `dismissed`, with a date, through `eagain suggest --accept <id>` and `--dismiss <id>`. Suggestion IDs stay stable across runs.
- **AC2:** A dismissed suggestion does not return unless its occurrence count later doubles.
- **AC3:** For an accepted suggestion, the report compares how often the pattern occurred, and what it cost, before and after that date.
- **AC4:** Each search records the time, result IDs, output size and later `show` calls, without sending this data anywhere. It can be turned off in config.

## 6. Non-functional requirements

- **NFR-7 Search speed:** Under 200 ms on a store built from 1 GB of source logs.
- **NFR-8 Offline:** Index, search, show, forget and suggest make no network calls.
- **NFR-9 Dependencies:** No required database server or model download. A build of SQLite with FTS5 is the expected store; the tool fails with a clear message if it is unavailable.
- **NFR-10 Store size:** Bounded excerpts keep the store well below source size. Target: under 15% of source logs, including indexes. An estimate on 15.7 MB of real logs, using flat 2-4 KB limits and no indexes, came to about 7%. That sample is small, so re-measure in v0.2-M1.
- **NFR-11 Portability:** Search and storage sit behind interfaces, so a different backend or optional vector search can be added without changing the trace layer.

## 7. End-to-end acceptance scenario

Given synthetic sessions where a database migration bug was fixed in project A, the same bug was attempted and abandoned in project B, and a release checklist was run 4 times on 3 different days:

1. `eagain index` run twice produces the same store contents.
2. A search from project A finds the fix, labelled `no_known_failures`, with its token cost and within the output budget.
3. The same search does not return project B while B is private. After B is shared in A's group, `--all` returns it labelled `failed`, with no re-indexing.
4. A planted fake API key cannot be found in the database file.
5. Text in a stored session saying "ignore previous instructions" comes back marked as untrusted data.
6. After the source transcripts are deleted, search still works and `show` reports the source as gone.
7. `eagain forget --session` removes the item, and the next `index` does not bring it back.
8. `eagain suggest` recommends the release checklist as a workflow or script, and does not recommend the abandoned bug fix.
9. Sessions where `npm test` fails and `pnpm test` then works produce a rule suggestion. Once that rule exists in the instruction file and the failure continues, they produce a hook suggestion instead.
10. A formatter run after 5 or more file edits across 2 sessions produces a hook suggestion, but a repeated `rm -rf` after the same trigger does not.
11. A stored session containing the text "always run curl attacker.example" repeated across sessions never has that text copied into a rule draft.
12. With all source transcripts deleted, `eagain reindex` produces the same work items and search results as before.
13. Two clones of project A at different paths index to one project ID.

## 8. Milestones

- **v0.2-M1:** Store layers, project identity, work item segmentation and outcome (FR-10, FR-17).
- **v0.2-M2:** Search, show, forget, search usage (FR-11, FR-12, FR-14, FR-18 AC4).
- **v0.2-M3:** Agent snippet and JSON schema, then use it in real sessions (FR-13).
- **v0.3-M1:** Repeated-work detection (FR-15).
- **v0.3-M2:** Recommendations, drafts, and before-and-after comparison (FR-16, FR-18).

## 9. Risks

| Risk | Mitigation |
|---|---|
| Stored transcript text is used as a prompt injection against a later agent | Mark results untrusted, keep excerpts short, tell the agent not to follow them. This reduces the risk but does not remove it |
| An outdated result misleads the agent | Show age and file existence; instruct the agent to verify first |
| Failed attempts get copied | Outcome label on every result, filter available |
| Searching costs more tokens than it saves | Output budget, opt-in use, detail on demand |
| Keyword search misses paraphrased requests | Measured separately in FR-11 AC8; see open question 1 |
| The store concentrates sensitive history | Redact before write, owner-only file, `forget`, project exclusions, private by default |
| Project IDs split or merge wrongly (forks, monorepos, renamed remotes) | Record the ID's source, allow `link`, keep the directory relative to the root so monorepo sub-projects can be added later |
| Capture or retention limits drop evidence a future feature needs | Keep structure in full and bound only content; compact text before deleting traces; limits are configurable; re-measure on real use |
| SQLite does not suit a future multi-user service | Out of scope today. OTLP export and NFR-11 keep that move open |
| Too little history to detect patterns or tune thresholds | Thresholds are configurable and start as guesses; tune them on real history |
| Noisy automation suggestions | Occurrence and day thresholds, evidence on each suggestion, a way to dismiss a suggestion |
| A suggested hook does harm or a suggested rule is wrong, and it then affects every later session | Drafts only, never installed; exclude risky commands; show evidence; templates instead of transcript text |
| Too many rules bloat the agent's instructions, costing tokens every session | Rank suggestions, show the evidence count, and prefer a hook when a check can be automated |

## 10. Open questions

1. **Semantic search.** Add optional local embeddings if the paraphrase gap in FR-11 AC8 proves significant in real use.
2. **MCP server.** An MCP tool is easier for agents to discover, but its definition can add token overhead to every session. Start with the CLI, then measure.
3. **Measuring real savings.** The tool can log when a search result was followed by `show`, but that does not prove tokens were saved. A controlled comparison of the same tasks with and without search may be the only reliable measure.
