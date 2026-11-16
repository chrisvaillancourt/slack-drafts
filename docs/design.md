# slack-drafts design

## Problem

Chris iterates on Slack messages with coding agents: the agent drafts, Chris edits in the Slack UI, then asks the agent for another round. The agent can't see the Slack edits, so each round starts from a stale copy. Sending must stay with Chris.

## Options weighed (2026-11-16)

| Route | Result |
| --- | --- |
| Slack MCP (`slack-mcp-server`, OAuth `xoxp` token) | No draft tools. `drafts.list` rejects the token: `not_allowed_token_type`. |
| agent-browser on desktop Slack | Slack refuses `--remote-debugging-port` on its default profile ("requires --user-data-dir pointing outside the default profile"). Dead end. |
| agent-browser on web Slack (separate Chrome profile) | Works: read the full draft from the composer (`.ql-editor`). Needs a Chrome window and four UI steps a read, and depends on Slack's DOM. |
| Internal drafts API with the web client's session (`xoxc` token + `d` cookie) | Works from plain HTTP, no browser: one call a read. **Chosen.** Undocumented, so it can change without notice. |

## Verified API behavior

All tested against a real workspace on 2026-11-16, on throwaway drafts in the self-DM.

- Auth: form field `token=xoxc-…` plus cookie `d=xoxd-…`, POST to `https://<workspace>.slack.com/api/<method>`.
- `drafts.list` (`is_active=true`): unsent drafts. Each has `id`, `blocks` (one `rich_text`), `destinations` (`[{channel_id, user_ids?, thread_ts?}]`), `last_updated_ts`, `last_updated_client`, `date_scheduled`, `is_from_composer`, `file_ids`, `unfurl`, `is_sent`, `is_deleted`.
- `drafts.create` requires `client_msg_id`, `destinations`, `blocks`, `file_ids`, `is_from_composer`.
- `drafts.update` requires `draft_id`, `client_last_updated_ts`, `destinations`, `blocks`, `file_ids`. `client_last_updated_ts` is the writer's edit time: the server rejects any value not newer than the stored `last_updated_ts` with `draft_has_conflict`. There is no compare-and-swap on a base version.
- `drafts.delete` requires `draft_id`, `client_last_updated_ts`.
- Writes reject a destination holding both `channel_id` and `user_ids` (`both_user_ids_and_channel_id_provided_in_destination`), though `drafts.list` returns DM destinations that way. Writes send only `channel_id` and `thread_ts`.
- `last_updated_client` is `Slack SSB Mac (Atom)` for desktop, `Chrome` for the web client, and `Slack` for API writes like this tool's.
- Draft IDs aren't stable: editing in desktop Slack replaced a draft's ID. Look drafts up by destination (channel + thread), not ID.
- A real 49-line draft (nested lists, numbering continued past nested bullets, bold mentions, 17 links) survived `get` → `put` → `get` through Slack byte for byte.

## Desktop Slack and server-side writes

- An open composer does **not** update live when the draft changes on the server. It shows the new text after switching to another conversation and back.
- Typing into a stale composer saves the stale text plus the keystrokes over the server copy, silently (`last_updated_client: "Slack SSB Mac (Atom)"`). The agent's write is lost.

Consequences:
1. After every `put`, the CLI tells the user to switch conversations and back before editing.
2. `put` does its own conflict check against a **revision handle**: `get` prints `rev=<draft id>@<last_updated_ts>`, and `put --rev` re-reads the draft and refuses (exit 5) unless the same draft is still at that timestamp. The handle travels with the agent's own read, so one agent's read can't approve another's stale write. The window between the re-read and the write is small and accepted.
3. `get` warns when the draft changed after the agent's last write and looks more like the version before it (by `difflib` similarity), the signature of a stale message box saving over the write. `diff` shows what the agent wrote; history keeps it.

The design review (GPT-6.1 Sol, 2026-11-16) also proposed having the user leave the conversation *before* each write. Declined for the MVP: it adds a round trip to every write, and the overwrite is detected next round with the agent's text kept in history. Revisit if overwrites show up in practice.

## Safety

- The CLI can't send: its API helper allows only `auth.test`, `drafts.list`, `drafts.create`, `drafts.update`, `conversations.info` and `users.info`. Tests assert the list.
- It never sets `date_scheduled`, and refuses to write a scheduled draft (writing could change a scheduled send).
- A draft is writable only when it round-trips: rendered to Markdown and parsed back, it must equal the original blocks after canonicalizing (merged text runs, no style on whitespace). Anything else, including unknown element types, is read-only. There's no `--force`.
- Attached files (`file_ids`) are passed through unchanged on write.
- No delete command.
- `auth login` opens a dedicated Chrome profile with a debugging port (default 9333), waits for a logged-in Slack page, reads the `xoxc` token from `localStorage.localConfig_v2` and the `d` cookie through agent-browser in subprocesses whose output is never printed, verifies them with `auth.test`, stores them, then quits that Chrome. Desktop Slack's session can't be read this way (see the options table).
- Secrets live in the macOS login keychain (ACL trusts `/usr/bin/security`, as the Slack MCP launcher does), written through `security -i` on stdin so values never appear in argv. Env vars override for tests and other platforms. Nothing prints a token or cookie.
- History of reads and writes (draft text) lives in `~/.local/state/slack-drafts`, dirs 0700, files 0600, never in a repo.

## Text format

Agents read and write Slack-style Markdown (the same dialect as `clip`):

- Each line is a line; blank lines are kept.
- `- ` bullets and `1. ` numbers, nesting by two spaces a level; numbering continues after a nested list (`offset`).
- `> ` quotes, ```` ``` ```` fences.
- `*bold*` / `**bold**`, `_italic_`, `~strike~`, `` `code` ``, `[label](url)`.
- Mentions round-trip as `<@U123|Name>`, channels as `<#C123|name>`, `<!here>`/`<!channel>`/`<!everyone>`, emoji as `:name:`. The `|Name` part is for the reader; only the ID is sent.

Conversion goes both ways and is tested as a round trip: rich_text → Markdown → rich_text keeps the structure Slack's composer produces.

## Not in scope (MVP)

Multiple workspaces (one workspace a config), files and attachments, scheduled messages, deleting drafts, live sync into an open composer.
