# eagain

**Trying again is fine. Trying the same thing again is a spin loop.**

`eagain` will read your coding agents' session logs, show what keeps going wrong, find work they've already done, and suggest the rule, hook, script, workflow or skill that stops the repeat.

> **Status:** design stage. Nothing is built yet, and the commands below show the intended interface. See [`specs/`](specs/).

## The legend of the spinning process

*A work of fiction, with accurate syscalls.*

Long ago, in the age of slow disks, a young process asked the kernel for some data.

"`EAGAIN`," said the kernel. *Resource temporarily unavailable. Try again.*

So the process tried again. And again. And again, millions of times a second, pinning a CPU at 100% and heating the machine room, while the data it wanted was still crawling down the wire.

An old daemon, watching from its place in the process table, finally spoke. "The kernel never said *now*. `EAGAIN` means come back **when something has changed**." It showed the young process `epoll`, and taught it to sleep until the world was different. The fans went quiet, and programmers everywhere learned the lesson.

Decades later, a new kind of process woke up. It could write code and reason about it, and it spoke fluent English.

It ran `npm test`. *Command not found.* It ran `npm test` again. It read the config, apologised, and ran `npm test`. The next morning, in a brand new session with no memory of the last one, it did it all over again.

The CPU was fine this time. The meter was running in tokens.

Somewhere in the logs, every failed attempt was written down, and nobody ever read them. So the old daemon came out of retirement and started reading.

```console
$ eagain analyze --from claude-code
recurring-failure  `npm test` failed the same way in 6 sessions

$ eagain search "fix db migration"
you already solved this, 3 weeks ago

$ eagain suggest
rule  "Use pnpm test, not npm test"
hook  run the formatter after every edit
```

The agent can still fail, and it can still try again. It just has to change something first.

## What it will do

| Question | Command |
|---|---|
| What went wrong, and what keeps going wrong? | `eagain analyze` |
| Have we done this before? | `eagain search` |
| What should change so it stops happening? | `eagain suggest` |

It will run locally, keep your logs read-only, and make no network calls unless you explicitly ask for an LLM explanation.

## Why "EAGAIN"?

It's the Unix error for a call that can't complete right now: "Resource temporarily unavailable". The number depends on the system: 11 on Linux, 35 on macOS.

## License

[Apache-2.0](LICENSE)
