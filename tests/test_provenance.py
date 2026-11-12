"""Evaluation fingerprints must cover nested modules and be installation-independent."""

import tempfile
import unittest
from pathlib import Path

from evals.provenance import engine_digest


class EngineDigestTests(unittest.TestCase):
    def test_nested_source_changes_and_moves_are_recorded(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory)
            module = package / "model" / "card.py"
            module.parent.mkdir()
            module.write_text("VERSION = 1\n")
            original = engine_digest(package)
            module.write_text("VERSION = 2\n")
            changed = engine_digest(package)
            self.assertNotEqual(original, changed)
            module.rename(package / "card.py")
            self.assertNotEqual(changed, engine_digest(package))

    def test_install_location_and_non_source_files_do_not_change_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            package = Path(directory) / "checkout"
            package.mkdir()
            (package / "__init__.py").write_text("VERSION = 1\n")
            original = engine_digest(package)
            (package / "cache.pyc").write_bytes(b"cached bytecode")
            self.assertEqual(original, engine_digest(package))
            installed = package.rename(Path(directory) / "installed")
            self.assertEqual(original, engine_digest(installed))
