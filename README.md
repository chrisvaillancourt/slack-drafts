# slack-drafts

Let coding agents read and revise your unsent Slack drafts, your own edits included, without ever sending. Works with any harness that has a shell tool: Claude Code, omp, Codex and others.

When you refine a Slack message with an agent, you edit it in Slack between rounds and the agent never sees those edits. `slack-drafts` reads the draft as Slack has it saved and writes the agent's revision back as a draft. Sending stays with you.

## What's in it

| Part | For | Where |
| --- | --- | --- |
| `slack-drafts` CLI | the agent and you | `bin/slack-drafts` (a uv script, standard library only) |
| `slack-drafts` skill | tells agents when to read the draft and how to write it back safely | `skills/slack-drafts/SKILL.md` |

## Install

Requires macOS, [uv](https://docs.astral.sh/uv/), Google Chrome, and [agent-browser](https://github.com/vercel-labs/agent-browser) for the one-time login.

```sh
git clone <this repo> ~/dev/github/chrisvaillancourt/slack-drafts
~/dev/github/chrisvaillancourt/slack-drafts/install.sh   # links the CLI into ~/.local/bin and the skill into ~/.agents/skills and ~/.claude/skills
slack-drafts auth login                                  # opens Chrome; log in to your workspace once
```

`auth login` opens a dedicated Chrome profile (`~/.agent-browser-profiles/slack`), waits for you to log in, copies the web session's token and `d` cookie into the macOS login keychain (`slack-drafts.token`, `slack-drafts.cookie`), then quits that Chrome. The profile keeps the login, so running it again later needs no password. Run it again when commands exit 3.

## Use

```sh
slack-drafts list                    # unsent drafts, newest first
slack-drafts get                     # the newest draft as Markdown; stderr ends with rev=…
slack-drafts get 2                   # or a list number, channel ID, CHANNEL:THREAD_TS, or Slack URL
slack-drafts put --rev Dr0…@1794…  < revised.md   # write a revision, only if the draft is unchanged since that rev
slack-drafts diff                    # the agent's last write against the draft now
slack-drafts new C0123ABCD < first.md   # start a draft where there is none
```

`slack-drafts --help` and the script's docstring (`head -40 bin/slack-drafts`) have the Markdown dialect, exit codes and environment variables.

**After every write, switch to another conversation in Slack and back before you edit.** Slack's open message box doesn't refresh when the draft changes on the server, and typing into it saves the old text over the new. If that happens, the next `get` warns and `diff` shows what the agent wrote.

## How it's safe

- **No send path.** The CLI calls only `auth.test`, `drafts.list`, `drafts.create`, `drafts.update`, `conversations.info` and `users.info`, enforced in code and by a test. It has no delete, and it refuses to touch scheduled drafts.
- **No lost edits.** `put` needs the `rev` from `get` and refuses (exit 5) if the draft changed since, so an agent can't write over an edit it didn't see. Drafts with formatting the converter can't reproduce exactly are read-only.
- **Secrets stay out of output.** The token and cookie go from the browser to the keychain inside the CLI's own subprocesses and are never printed. History of reads and writes (your message text) is kept in `~/.local/state/slack-drafts` with private permissions.

It uses Slack's internal drafts API, the one the web client uses, which Slack doesn't document and could change. [docs/design.md](docs/design.md) has the options weighed, the verified API behavior and the limits.

## Development

```sh
uv run --no-project python -I -m unittest discover -s tests -v   # fake Slack API; no real Slack, keychain or network
```

[AGENTS.md](AGENTS.md) maps the repo for agents working on it.
