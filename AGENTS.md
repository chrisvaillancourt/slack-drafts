# Working on slack-drafts

`slack-drafts` lets agents read and revise unsent Slack drafts. It must never be able to send.

| Path | What |
| --- | --- |
| `bin/slack-drafts` | the CLI: one uv script, standard library only. Sections in order: converter (rich_text ↔ Markdown), paths and credentials, Slack API, names, refs and history, commands |
| `skills/slack-drafts/SKILL.md` | what agents are told to do; harness-neutral |
| `docs/design.md` | why it's built this way, verified Slack API behavior, desktop-Slack quirks, limits |
| `install.sh` | links the CLI and the skill |

## Checks

```sh
uv run --no-project python -I -m unittest discover -s tests -v
```

`tests/test_cli.py` runs the CLI against a fake Slack API (`SLACK_DRAFTS_API`) with env credentials, so tests never touch the real workspace or keychain. When the real API surprises you, teach the fake the same behavior first (it already rejects DM destinations with `user_ids`, as Slack does), get a red test, then fix.

## Rules

- `ALLOWED_METHODS` is the send guard. Adding a method needs a reason in `docs/design.md`; never add a `chat.*` method or anything that sets `date_scheduled`.
- Converter changes keep the round trip: `RoundTrip` cases in `tests/test_convert.py` hold shapes Slack's composer produces. Add a case for each new shape you support.
- Never print, log or record the token or cookie. Test new commands in `test_secrets_never_printed`.
- Live testing goes in the self-DM (`slack-drafts new <your self-DM channel ID>`), never a real conversation. There's no delete command; clean up a test draft by hand in Slack.
- When the skill's workflow changes, update `SKILL.md`, the README's Use section and the docstring together.
