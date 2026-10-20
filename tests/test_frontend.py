from html.parser import HTMLParser
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
STATIC = ROOT / "pocket_media_clip_selector" / "static"


class FrontendTests(unittest.TestCase):
    def test_static_control_ids_and_local_assets_exist(self):
        class PageParser(HTMLParser):
            ids = []
            assets = []

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if "id" in attributes:
                    self.ids.append(attributes["id"])
                for name in ["src", "href"]:
                    if attributes.get(name, "").startswith("/static/"):
                        self.assets.append(attributes[name])

        parser = PageParser()
        parser.feed((STATIC / "index.html").read_text())
        self.assertEqual(len(parser.ids), len(set(parser.ids)), "HTML IDs must be unique")
        referenced = set(re.findall(r'\$\("([a-z-]+)"\)', (STATIC / "app.js").read_text()))
        self.assertTrue(referenced.issubset(set(parser.ids)), referenced - set(parser.ids))
        for asset in parser.assets:
            self.assertTrue((STATIC / Path(asset).name).is_file())

    def test_bookmarks_quick_log_playback_and_lifecycle_behavior(self):
        runtime = shutil.which("node")
        jsc = Path("/System/Library/Frameworks/JavaScriptCore.framework/Versions/A/Helpers/jsc")
        if not runtime and jsc.is_file():
            runtime = str(jsc)
        if not runtime:
            self.skipTest(
                "Install Node.js to run optional frontend behavior tests; the app itself needs no Node.js."
            )
        helpers = (
            "\n".join((STATIC / name).read_text() for name in ["player.js", "bookmarks.js"])
            .replace("export function", "function")
            .replace("export const", "const")
        )
        app = (STATIC / "app.js").read_text()
        app = re.sub(r"^import .*?;\n", "", app, flags=re.MULTILINE)
        app = app.rsplit("void acquireControl();", 1)[0]
        source = (
            (ROOT / "tests" / "frontend_harness.js").read_text()
            + "\n"
            + helpers
            + "\n"
            + app
            + "\n"
            + (ROOT / "tests" / "timestamp_checks.js").read_text()
            + "\n"
            + (ROOT / "tests" / "frontend_checks.js").read_text()
        )
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "checks.js"
            path.write_text(source, encoding="utf-8")
            result = subprocess.run(
                [runtime, str(path)], capture_output=True, text=True, timeout=20
            )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("Frontend behavior checks passed", result.stdout)
