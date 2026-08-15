from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_module(name: str, relative_path: str):
    path = ROOT / relative_path
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DocumentationTests(unittest.TestCase):
    def test_catalog_covers_all_skill_folders_and_generated_docs_are_current(self) -> None:
        module = load_module("docs_generator", "scripts/generate_docs.py")
        site, catalog = module.load_catalog()
        skills = module.validate_catalog(catalog)
        self.assertEqual(len(skills), 7)
        self.assertEqual(module.write_files(module.outputs(site, skills), check=True), [])

    def test_wiki_sync_only_removes_previously_generated_pages(self) -> None:
        module = load_module("wiki_sync", "scripts/sync_wiki.py")
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source, target = root / "source", root / "target"
            source.mkdir()
            target.mkdir()
            (source / "Home.md").write_text("new home", encoding="utf-8")
            (source / ".searchcans-generated-pages").write_text("Home.md\n", encoding="utf-8")
            (target / "Home.md").write_text("old home", encoding="utf-8")
            (target / "Retired.md").write_text("old generated", encoding="utf-8")
            (target / "Manual-Note.md").write_text("keep me", encoding="utf-8")
            (target / ".searchcans-generated-pages").write_text("Home.md\nRetired.md\n", encoding="utf-8")
            original_argv = __import__("sys").argv
            try:
                __import__("sys").argv = ["sync_wiki.py", "--source", str(source), "--target", str(target)]
                self.assertEqual(module.main(), 0)
            finally:
                __import__("sys").argv = original_argv
            self.assertEqual((target / "Home.md").read_text(encoding="utf-8"), "new home")
            self.assertFalse((target / "Retired.md").exists())
            self.assertTrue((target / "Manual-Note.md").exists())
