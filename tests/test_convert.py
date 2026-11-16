"""Converter tests: Slack rich_text blocks <-> the Markdown agents read and write.

Run: uv run --no-project python -I -m unittest discover -s tests -v
"""

import unittest

from _load import sd


def sec(*els):
    return {"type": "rich_text_section", "elements": list(els)}


def t(text, **style):
    el = {"type": "text", "text": text}
    if style:
        el["style"] = style
    return el


def blist(style, indent, *items, offset=0):
    el = {"type": "rich_text_list", "style": style, "elements": list(items)}
    if indent:
        el["indent"] = indent
    if offset:
        el["offset"] = offset
    return el


def rt(*els):
    return [{"type": "rich_text", "elements": list(els)}]


def norm(blocks):
    """Structure only: drop ids and default-valued keys Slack adds."""
    out = []
    for b in blocks:
        els = []
        for e in b["elements"]:
            e = {k: v for k, v in e.items() if k not in ("block_id", "border") and not (k in ("indent", "offset") and v == 0)}
            els.append(e)
        out.append({"type": b["type"], "elements": els})
    return out


class ToMarkdown(unittest.TestCase):
    def md(self, blocks, names=None):
        text, unsupported = sd.blocks_to_md(blocks, names or {})
        self.assertEqual(unsupported, [])
        return text

    def test_plain_lines_and_blank_lines(self):
        self.assertEqual(self.md(rt(sec(t("one\n\ntwo")))), "one\n\ntwo")

    def test_styles(self):
        blocks = rt(sec(t("a "), t("bold", bold=True), t(" "), t("it", italic=True), t(" "),
                        t("gone", strike=True), t(" "), t("x()", code=True)))
        self.assertEqual(self.md(blocks), "a *bold* _it_ ~gone~ `x()`")

    def test_style_hugs_text(self):
        # Slack may put the space inside the bold run; markers must hug the word.
        self.assertEqual(self.md(rt(sec(t("Note. ", bold=True), t("more text")))), "*Note.* more text")

    def test_links_mentions_emoji(self):
        blocks = rt(sec(
            {"type": "user", "user_id": "U0ANN12345"}, t(" see "),
            {"type": "link", "url": "https://x.test/PLAT-1", "text": "PLAT-1"}, t(" and "),
            {"type": "link", "url": "https://x.test/raw"}, t(" "),
            {"type": "channel", "channel_id": "C1"}, t(" "),
            {"type": "broadcast", "range": "here"}, t(" "),
            {"type": "emoji", "name": "tada"},
        ))
        self.assertEqual(
            self.md(blocks, {"U0ANN12345": "Ann Example", "C1": "dev"}),
            "<@U0ANN12345|Ann Example> see [PLAT-1](https://x.test/PLAT-1) and https://x.test/raw <#C1|dev> <!here> :tada:",
        )

    def test_bold_mention(self):
        blocks = rt(sec({"type": "user", "user_id": "U1", "style": {"bold": True}}))
        self.assertEqual(self.md(blocks, {"U1": "Ann"}), "*<@U1|Ann>*")

    def test_lists_nest_and_continue_numbering(self):
        blocks = rt(
            sec(t("Plan:")),
            blist("ordered", 0, sec(t("first"))),
            blist("bullet", 1, sec(t("detail a")), sec(t("detail b"))),
            blist("ordered", 0, sec(t("second")), offset=1),
            sec(t("after")),
        )
        self.assertEqual(self.md(blocks), "Plan:\n1. first\n  - detail a\n  - detail b\n2. second\nafter")

    def test_quote_and_code_block(self):
        blocks = rt(
            {"type": "rich_text_quote", "elements": [t("quoted\nline two")]},
            {"type": "rich_text_preformatted", "elements": [t("x = 1\ny = 2")]},
        )
        self.assertEqual(self.md(blocks), "> quoted\n> line two\n```\nx = 1\ny = 2\n```")

    def test_literal_markers_are_escaped(self):
        # Text that would parse as formatting on the way back gets a backslash.
        self.assertEqual(self.md(rt(sec(t("*not bold* and snake_case_name")))), "\\*not bold\\* and snake_case_name")
        self.assertEqual(self.md(rt(sec(t("- not a list")))), "\\- not a list")

    def test_unsupported_elements_are_reported(self):
        text, unsupported = sd.blocks_to_md(rt(sec(t("on "), {"type": "date", "timestamp": 1})), {})
        self.assertEqual(unsupported, ["date"])
        self.assertIn("unsupported", text)


class ToBlocks(unittest.TestCase):
    def blocks(self, md):
        return norm(sd.md_to_blocks(md))

    def test_plain(self):
        self.assertEqual(self.blocks("one\n\ntwo"), rt(sec(t("one\n\ntwo"))))

    def test_styles(self):
        self.assertEqual(
            self.blocks("a *bold* **also** _it_ ~gone~ `x()`"),
            rt(sec(t("a "), t("bold", bold=True), t(" "), t("also", bold=True), t(" "), t("it", italic=True),
                   t(" "), t("gone", strike=True), t(" "), t("x()", code=True))),
        )

    def test_intraword_underscore_and_times_stay_literal(self):
        self.assertEqual(self.blocks("snake_case_name at 10:30:45"), rt(sec(t("snake_case_name at 10:30:45"))))

    def test_links_mentions(self):
        self.assertEqual(
            self.blocks("<@U1|Ann> [PLAT-1](https://x.test/PLAT-1) https://x.test/raw. <#C1> <!here> :tada:"),
            rt(sec({"type": "user", "user_id": "U1"}, t(" "),
                   {"type": "link", "url": "https://x.test/PLAT-1", "text": "PLAT-1"}, t(" "),
                   {"type": "link", "url": "https://x.test/raw"}, t(". "),
                   {"type": "channel", "channel_id": "C1"}, t(" "),
                   {"type": "broadcast", "range": "here"}, t(" "),
                   {"type": "emoji", "name": "tada"})),
        )

    def test_slack_style_link(self):
        self.assertEqual(self.blocks("<https://x.test|label>"),
                         rt(sec({"type": "link", "url": "https://x.test", "text": "label"})))

    def test_lists(self):
        self.assertEqual(
            self.blocks("Plan:\n1. first\n  - detail\n2. second\n\nafter"),
            rt(sec(t("Plan:")),
               blist("ordered", 0, sec(t("first"))),
               blist("bullet", 1, sec(t("detail"))),
               blist("ordered", 0, sec(t("second")), offset=1),
               sec(t("\nafter"))),
        )

    def test_bullet_markers(self):
        self.assertEqual(self.blocks("* a\n• b"), rt(blist("bullet", 0, sec(t("a")), sec(t("b")))))

    def test_quote_and_fence(self):
        self.assertEqual(
            self.blocks("> quoted *b*\n> two\n```\nx = *1*\n```"),
            rt({"type": "rich_text_quote", "elements": [t("quoted "), t("b", bold=True), t("\ntwo")]},
               {"type": "rich_text_preformatted", "elements": [t("x = *1*")]}),
        )

    def test_escapes(self):
        self.assertEqual(self.blocks("\\*lit\\* \\- x"), rt(sec(t("*lit* - x"))))


class RoundTrip(unittest.TestCase):
    """blocks -> md -> blocks keeps structure for what Slack's composer produces."""

    CASES = [
        rt(sec(t("Hi "), {"type": "user", "user_id": "U1"}, t(" and "), {"type": "user", "user_id": "U2"},
               t("\nHere is the plan.\n\n"), t("Status", bold=True)),
           blist("bullet", 0, sec(t("the build has:"))),
           blist("bullet", 1, sec(t("part one")), sec(t("part two"))),
           blist("bullet", 0, sec(t("Open: "), {"type": "link", "url": "https://j.test/A-1", "text": "A-1"}, t(" and more"))),
           sec(t("\n"), {"type": "user", "user_id": "U1", "style": {"bold": True}}, t("\n")),
           blist("ordered", 0, sec(t("First.", bold=True), t(" Do the thing."))),
           blist("bullet", 1, sec(t("a")), sec(t("b"))),
           blist("ordered", 0, sec(t("Second", bold=True), t(" then this.")), offset=1)),
        rt(sec(t("code "), t("a_b", code=True), t(" and "), t("x", bold=True, italic=True))),
        rt(sec(t("price is $5 * 3 = $15 and 2 < 3"))),
        rt(sec(t("trailing blank\n")), blist("bullet", 0, sec(t("x")))),
    ]

    def test_round_trip(self):
        for blocks in self.CASES:
            with self.subTest(blocks=blocks):
                md, unsupported = sd.blocks_to_md(blocks, {})
                self.assertEqual(unsupported, [])
                self.assertEqual(norm(sd.md_to_blocks(md)), norm(blocks), md)

    def test_styled_whitespace_counts_as_lossless(self):
        # Slack's composer leaves bold on a lone space; bold whitespace is invisible.
        blocks = rt(sec(t("Status", bold=True), t(" ", bold=True), t("\n\nnext")))
        self.assertTrue(sd.lossless(blocks))

    def test_md_round_trip(self):
        md = "Hi <@U1|Ann>\n\n*Plan*\n1. *First.* key it\n  - [A-1](https://j.test/A-1)\n2. ship\n> note\n```\ncode\n```"
        blocks = sd.md_to_blocks(md)
        back, _ = sd.blocks_to_md(blocks, {"U1": "Ann"})
        self.assertEqual(back, md)


if __name__ == "__main__":
    unittest.main()
