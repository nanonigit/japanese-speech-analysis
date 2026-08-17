from __future__ import annotations

import subprocess
import os
from tempfile import TemporaryDirectory
import unittest
from pathlib import Path


class ConsoleLauncherTests(unittest.TestCase):
    def test_launcher_describes_fluency_range_output_and_checks_range_dependencies(self) -> None:
        launcher = Path("run_jgrade_console.command")
        contents = launcher.read_text(encoding="utf-8")

        self.assertIn("Fluency客観データ", contents)
        self.assertIn("Range客観データ", contents)
        self.assertIn("from jgrade_eval.range import RangeExtractor; RangeExtractor.default()", contents)
        self.assertIn("uv sync --frozen", contents)

    def test_launcher_has_valid_zsh_syntax(self) -> None:
        result = subprocess.run(
            ["zsh", "-n", "run_jgrade_console.command"],
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_launcher_stops_before_audio_processing_when_range_dependencies_are_missing(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            fake_python = Path(temporary_directory) / "python"
            fake_python.write_text("#!/bin/zsh\nexit 1\n", encoding="utf-8")
            fake_python.chmod(0o755)
            environment = {
                **os.environ,
                "JGRADE_PYTHON_BIN": str(fake_python),
                "TERM": "dumb",
            }
            result = subprocess.run(
                ["zsh", "run_jgrade_console.command"],
                check=False,
                capture_output=True,
                text=True,
                env=environment,
            )

        self.assertEqual(result.returncode, 1)
        self.assertIn("Rangeモジュールに必要なSudachiPy辞書", result.stdout)
        self.assertIn("uv sync --frozen", result.stdout)
        self.assertNotIn("音声ファイルを選択してください", result.stdout)


if __name__ == "__main__":
    unittest.main()
