"""Command tests against a fake Slack API. No real Slack, keychain or clipboard.

Run: uv run --no-project python -I -m unittest discover -s tests -v
"""

import http.server
import json
import os
import pathlib
import subprocess
import tempfile
import threading
import unittest
import urllib.parse

from _load import SCRIPT, sd


def draft(id_, ts, text, channel="C0TEST", thread=None, scheduled=0, blocks=None, client="Slack SSB Mac (Atom)"):
    dest = {"channel_id": channel}
    if thread:
        dest["thread_ts"] = thread
    return {
        "id": id_, "last_updated_ts": ts, "last_updated_client": client, "date_scheduled": scheduled,
        "is_from_composer": True, "is_sent": False, "is_deleted": False, "file_ids": [],
        "destinations": [dest],
        "blocks": blocks or [{"type": "rich_text", "elements": [
            {"type": "rich_text_section", "elements": [{"type": "text", "text": text}]}]}],
    }


class FakeSlack:
    def __init__(self):
        self.drafts = []
        self.calls = []
        fake = self

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def do_POST(self):
                method = self.path.rsplit("/", 1)[-1]
                body = self.rfile.read(int(self.headers["Content-Length"])).decode()
                form = {k: v[0] for k, v in urllib.parse.parse_qs(body).items()}
                fake.calls.append((method, form, self.headers.get("Cookie")))
                resp = fake.handle(method, form)
                data = json.dumps(resp).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/"

    def handle(self, method, form):
        if form.get("token") != "xoxc-test":
            return {"ok": False, "error": "invalid_auth"}
        if method == "drafts.list":
            return {"ok": True, "drafts": self.drafts}
        if method in ("drafts.update", "drafts.create"):
            # Real Slack lists DM destinations with user_ids but rejects them on write.
            if any("user_ids" in x and "channel_id" in x for x in json.loads(form["destinations"])):
                return {"ok": False, "error": "both_user_ids_and_channel_id_provided_in_destination"}
        if method == "drafts.update":
            d = next((x for x in self.drafts if x["id"] == form["draft_id"]), None)
            if not d:
                return {"ok": False, "error": "draft_not_found"}
            if float(form["client_last_updated_ts"]) <= float(d["last_updated_ts"]):
                return {"ok": False, "error": "draft_has_conflict"}
            d["blocks"] = json.loads(form["blocks"])
            d["last_updated_ts"] = form["client_last_updated_ts"]
            d["last_updated_client"] = "slack-drafts"
            return {"ok": True, "draft": d}
        if method == "drafts.create":
            d = draft("DrNEW", "1800000000.000001", "")
            d["blocks"] = json.loads(form["blocks"])
            d["destinations"] = json.loads(form["destinations"])
            self.drafts.append(d)
            return {"ok": True, "draft": d}
        if method == "users.info":
            return {"ok": True, "user": {"profile": {"real_name": "Ann Example"}}}
        if method == "conversations.info":
            return {"ok": True, "channel": {"name": "general"}}
        if method == "auth.test":
            return {"ok": True, "user": "me", "user_id": "U0ME", "url": "https://acme.slack.com/"}
        return {"ok": False, "error": "unknown_method"}

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class CLITest(unittest.TestCase):
    def setUp(self):
        self.fake = FakeSlack()
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {
            "PATH": os.environ["PATH"], "HOME": self.tmp.name, "LOGNAME": "test",
            "SLACK_DRAFTS_TOKEN": "xoxc-test", "SLACK_DRAFTS_COOKIE": "xoxd-test",
            "SLACK_DRAFTS_API": self.fake.url,
            "SLACK_DRAFTS_STATE_DIR": str(pathlib.Path(self.tmp.name) / "state"),
            "SLACK_DRAFTS_CONFIG_DIR": str(pathlib.Path(self.tmp.name) / "config"),
        }

    def tearDown(self):
        self.fake.close()
        self.tmp.cleanup()

    def run_cli(self, *args, stdin=""):
        return subprocess.run([str(SCRIPT), *args], input=stdin, capture_output=True, text=True, env=self.env, timeout=60)

    def rev(self, result):
        return next(line.split("rev=", 1)[1] for line in (result.stderr + result.stdout).splitlines() if "rev=" in line)

    def methods(self):
        return {m for m, _, _ in self.fake.calls}

    def test_get_prints_markdown_and_rev(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "hello *world*")]
        r = self.run_cli("get")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout, "hello \\*world\\*\n")
        self.assertEqual(self.rev(r), "Dr1@1700008619.938185")
        self.assertIn("#general", r.stderr)
        self.assertEqual(self.fake.calls[0][2], "d=xoxd-test")

    def test_put_writes_when_rev_matches(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "v1")]
        rev = self.rev(self.run_cli("get"))
        r = self.run_cli("put", "--rev", rev, stdin="v2 with *bold*\n")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("switch to another conversation", r.stderr)
        els = self.fake.drafts[0]["blocks"][0]["elements"][0]["elements"]
        self.assertEqual(els, [{"type": "text", "text": "v2 with "}, {"type": "text", "text": "bold", "style": {"bold": True}}])
        self.assertNotEqual(self.rev(r), rev)

    def test_put_to_a_dm_sends_only_the_channel(self):
        d = draft("Dr1", "1700008619.938185", "v1", channel="D0AAAAAAA")
        d["destinations"][0]["user_ids"] = ["U0ME", "U0ANN"]
        self.fake.drafts = [d]
        r = self.run_cli("put", "--rev", "Dr1@1700008619.938185", stdin="v2")
        self.assertEqual(r.returncode, 0, r.stderr)
        sent = json.loads(next(f for m, f, _ in self.fake.calls if m == "drafts.update")["destinations"])
        self.assertEqual(sent, [{"channel_id": "D0AAAAAAA"}])

    def test_put_refuses_when_draft_changed(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "v1")]
        rev = self.rev(self.run_cli("get"))
        self.fake.drafts[0]["last_updated_ts"] = "1700008700.000000"  # Chris edited in Slack
        r = self.run_cli("put", "--rev", rev, stdin="agent text")
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertNotIn("drafts.update", self.methods())

    def test_put_refuses_when_draft_was_resaved_under_new_id(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "v1")]
        rev = self.rev(self.run_cli("get"))
        self.fake.drafts = [draft("Dr2", "1700008700.000000", "v1 edited")]
        r = self.run_cli("put", "--rev", rev, stdin="agent text")
        self.assertEqual(r.returncode, 5, r.stderr)
        self.assertNotIn("drafts.update", self.methods())

    def test_put_refuses_scheduled_draft(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "v1", scheduled=1800000000)]
        r = self.run_cli("put", "--rev", "Dr1@1700008619.938185", stdin="x")
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertNotIn("drafts.update", self.methods())

    def test_put_refuses_lossy_draft(self):
        blocks = [{"type": "rich_text", "elements": [{"type": "rich_text_section", "elements": [
            {"type": "text", "text": "on "}, {"type": "date", "timestamp": 1800000000}]}]}]
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "", blocks=blocks)]
        g = self.run_cli("get")
        self.assertIn("read-only", g.stderr)
        r = self.run_cli("put", "--rev", self.rev(g), stdin="x")
        self.assertEqual(r.returncode, 6, r.stderr)
        self.assertNotIn("drafts.update", self.methods())

    def test_put_requires_rev(self):
        r = self.run_cli("put", stdin="x")
        self.assertEqual(r.returncode, 2)

    def test_resolve_by_channel_thread_and_url(self):
        self.fake.drafts = [draft("DrA", "1700008619.000001", "top", channel="C0AAAAAAA"),
                            draft("DrB", "1700008619.000002", "thread", channel="C0AAAAAAA", thread="1700000000.123456")]
        self.assertEqual(self.run_cli("get", "C0AAAAAAA").stdout, "top\n")
        self.assertEqual(self.run_cli("get", "C0AAAAAAA:1700000000.123456").stdout, "thread\n")
        url = "https://acme.slack.com/archives/C0AAAAAAA/p1700000000123456"
        self.assertEqual(self.run_cli("get", url).stdout, "thread\n")
        self.assertEqual(self.run_cli("get", "C0ZZZZZZZ").returncode, 2)

    def test_new_refuses_when_a_draft_exists(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "v1", channel="C0AAAAAAA")]
        r = self.run_cli("new", "C0AAAAAAA", stdin="x")
        self.assertEqual(r.returncode, 5)
        r = self.run_cli("new", "C0BBBBBBB", stdin="hi *there*")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("drafts.create", self.methods())

    def test_get_warns_when_stale_composer_overwrote_the_write(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "the original long message from chris")]
        rev = self.rev(self.run_cli("get"))
        self.run_cli("put", "--rev", rev, stdin="a completely rewritten version by the agent\n")
        # Desktop Slack saves its stale copy plus a keystroke over the agent's write.
        self.fake.drafts[0]["blocks"] = draft("x", "0", "the original long message from chris!")["blocks"]
        self.fake.drafts[0]["last_updated_ts"] = "1900000000.000000"
        r = self.run_cli("get")
        self.assertIn("saved over it", r.stderr)
        d = self.run_cli("diff")
        self.assertIn("+the original long message from chris!", d.stdout)

    def test_no_warning_after_a_normal_edit_on_top_of_the_write(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "the original long message from chris")]
        rev = self.rev(self.run_cli("get"))
        self.run_cli("put", "--rev", rev, stdin="a completely rewritten version by the agent\n")
        self.fake.drafts[0]["blocks"] = draft("x", "0", "a completely rewritten version by the agent, tweaked")["blocks"]
        self.fake.drafts[0]["last_updated_ts"] = "1900000000.000000"
        self.assertNotIn("saved over it", self.run_cli("get").stderr)

    def test_auth_error_exits_3(self):
        self.env["SLACK_DRAFTS_TOKEN"] = "xoxc-wrong"
        r = self.run_cli("list")
        self.assertEqual(r.returncode, 3)
        self.assertIn("auth login", r.stderr)

    def test_secrets_never_printed(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "v1")]
        for args in (["list"], ["get"], ["get", "--json"], ["auth", "status"]):
            r = self.run_cli(*args)
            self.assertNotIn("xoxc-test", r.stdout + r.stderr)
            self.assertNotIn("xoxd-test", r.stdout + r.stderr)

    def test_history_is_private(self):
        self.fake.drafts = [draft("Dr1", "1700008619.938185", "v1")]
        self.run_cli("get")
        files = list((pathlib.Path(self.env["SLACK_DRAFTS_STATE_DIR"]) / "drafts").iterdir())
        self.assertTrue(files)
        for f in files:
            self.assertEqual(f.stat().st_mode & 0o777, 0o600)
        self.assertEqual(f.parent.stat().st_mode & 0o777, 0o700)


class Safety(unittest.TestCase):
    def test_only_draft_and_lookup_methods_are_allowed(self):
        self.assertEqual(sd.ALLOWED_METHODS, frozenset(
            {"auth.test", "drafts.list", "drafts.create", "drafts.update", "conversations.info", "users.info"}))
        for m in ("chat.postMessage", "chat.scheduleMessage", "drafts.delete", "chat.update"):
            with self.subTest(method=m), self.assertRaises(sd.Fail) as cm:
                sd.api(m, {}, creds=("t", "c", "127.0.0.1:9"))
            self.assertEqual(cm.exception.code, sd.EXIT_REFUSED)

    def test_source_never_names_a_send_method(self):
        source = SCRIPT.read_text()
        for m in ("chat.postMessage", "chat.scheduleMessage", "chat.meMessage", "date_scheduled\":"):
            self.assertNotIn(m, source)


if __name__ == "__main__":
    unittest.main()
