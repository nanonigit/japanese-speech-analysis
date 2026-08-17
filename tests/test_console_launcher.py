from __future__ import annotations

import subprocess
import unittest
from pathlib import Path


class ConsoleLauncherTests(unittest.TestCase):
    def test_launcher_describes_fluency_range_output_and_checks_range_dependencies(self) -> None:
        launcher = Path("run_jgrade_console.command")
        contents = launcher.read_text(encoding="utf-8")

        self.assertIn("Fluency客観データ", contents)
        self.assertIn("Range客観データ", contents)
        self.assertIn("import sudachipy, sudachidict_core", contents)
        self.assertIn("uv sync --frozen", contents)

    def test_launcher_has_valid_zsh_syntax(self) -> None:
        result = subprocess.run(
            ["zsh", "-n", "run_jgrade_console.command"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
