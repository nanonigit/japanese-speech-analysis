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

    def test_readme_and_launcher_explain_first_run_network_requirements(self) -> None:
        first_run_notice = (
            "初回のみ、uvによる依存関係導入と音声認識モデルの取得には、"
            "ネットワーク接続と時間が必要です。"
        )
        readme = Path("README.md").read_text(encoding="utf-8")
        launcher = Path("run_jgrade_console.command").read_text(encoding="utf-8")

        self.assertIn(first_run_notice, readme)
        self.assertIn(first_run_notice, launcher)

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
