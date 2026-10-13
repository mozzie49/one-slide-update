"""First-use regression: only the installed skill is available to the helper."""
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "one-slide-update"
NS = {"a": "http://schemas.openxmlformats.org/drawingml/2006/main"}


class FirstUseTests(unittest.TestCase):
    def test_demo_sources_match_published_fictional_example(self):
        demo = json.loads((SKILL / "assets/demo/relay-update.json").read_text())
        original = json.loads((ROOT / "examples/inputs/relay-update.json").read_text())
        # The provenance path is the only changed fact: it must survive install.
        self.assertEqual(demo["source_notes"][1],
                         "Source: assets/demo/relay-weekly-notes.md, as of 1 October 2026.")
        demo["source_notes"][1] = original["source_notes"][1]
        self.assertEqual(demo, original)
        self.assertEqual((SKILL / "assets/demo/relay-weekly-notes.md").read_bytes(),
                         (ROOT / "examples/inputs/relay-weekly-notes.md").read_bytes())

    def test_installed_demo_fills_checks_and_preserves_visible_example(self):
        for host in (".agents", ".claude"):
            for layout in ("standard", "blocker", "milestone"):
                with self.subTest(host=host, layout=layout), tempfile.TemporaryDirectory() as tmp:
                    project = Path(tmp) / "project"
                    installed = project / host / "skills" / "one-slide-update"
                    shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("__pycache__"))
                    script = installed / "scripts/fill_update.py"
                    fixture = installed / "assets/demo/relay-update.json"
                    original = fixture.read_bytes()
                    output = project / "my-update.pptx"
                    fill = subprocess.run(
                        [sys.executable, str(script), "fill", str(fixture), str(output),
                         "--layout", layout],
                        cwd=project, capture_output=True, text=True)
                    self.assertEqual(fill.returncode, 0, fill.stderr)
                    check = subprocess.run(
                        [sys.executable, str(script), "check", str(output), "--layout", layout],
                        cwd=project, capture_output=True, text=True)
                    self.assertEqual(check.returncode, 0, check.stderr)
                    self.assertEqual(json.loads(check.stdout)["result"], "PASS")
                    self.assertEqual(fixture.read_bytes(), original)
                    with zipfile.ZipFile(output) as actual, zipfile.ZipFile(
                            ROOT / f"examples/outputs/relay-{layout}.pptx") as expected:
                        # Slide bytes match the already-rendered published example.
                        self.assertEqual(actual.read("ppt/slides/slide1.xml"),
                                         expected.read("ppt/slides/slide1.xml"))
                        slide = ET.fromstring(actual.read("ppt/slides/slide1.xml"))
                        text = "\n".join(t.text or "" for t in slide.findall(".//a:t", NS))
                        for phrase in ("Pilot waits on export permissions", "At risk",
                                       "24 October", "Owner not provided"):
                            self.assertIn(phrase, text)
                        self.assertNotIn("%", text)
                        self.assertIn(b"assets/demo/relay-weekly-notes.md",
                                      actual.read("ppt/notesSlides/notesSlide1.xml"))

    def test_installed_demo_refuses_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            installed = project / ".agents/skills/one-slide-update"
            shutil.copytree(SKILL, installed, ignore=shutil.ignore_patterns("__pycache__"))
            output = project / "my-update.pptx"
            output.write_bytes(b"KEEP USER FILE")
            result = subprocess.run(
                [sys.executable, str(installed / "scripts/fill_update.py"), "fill",
                 str(installed / "assets/demo/relay-update.json"), str(output),
                 "--layout", "blocker"],
                cwd=project, capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)
            self.assertIn("already exists", result.stderr)
            self.assertEqual(output.read_bytes(), b"KEEP USER FILE")


if __name__ == "__main__":
    unittest.main()
