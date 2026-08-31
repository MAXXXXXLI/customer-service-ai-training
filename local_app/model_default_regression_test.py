#!/usr/bin/env python3
"""Keep the default model and browser persistence contract in sync."""

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parent
FAST_MODEL = "Qwen/Qwen3.5-27B"


class ModelDefaultRegressionTest(unittest.TestCase):
    def test_server_and_browser_default_to_fast_model(self) -> None:
        server = (ROOT / "server.py").read_text(encoding="utf-8")
        app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn(f'DEFAULT_MODEL = os.getenv("SILICONFLOW_MODEL", "{FAST_MODEL}")', server)
        self.assertRegex(app, rf'const DEFAULT_MODEL = "{re.escape(FAST_MODEL)}";')

    def test_browser_versions_model_storage_for_existing_visitors(self) -> None:
        app = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        self.assertIn('const MODEL_STORAGE_KEY = "kbai_model_v2";', app)
        self.assertIn('localStorage.getItem(MODEL_STORAGE_KEY) || DEFAULT_MODEL', app)
        self.assertGreaterEqual(app.count('localStorage.setItem(MODEL_STORAGE_KEY, state.model)'), 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
