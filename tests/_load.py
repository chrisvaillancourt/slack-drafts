"""Load bin/slack-drafts (a script with no .py suffix) as a module for tests."""

import importlib.machinery
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "bin" / "slack-drafts"

_loader = importlib.machinery.SourceFileLoader("slack_drafts", str(SCRIPT))
_spec = importlib.util.spec_from_loader("slack_drafts", _loader)
sd = importlib.util.module_from_spec(_spec)
_loader.exec_module(sd)
