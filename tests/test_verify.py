"""検証ランナーの終了・timeout・起動失敗を成功扱いしない。"""

from pathlib import Path
import sys
import tempfile
import unittest

from scripts.verify import run_command


class VerificationRunnerTests(unittest.TestCase):
    def test_status_and_full_diagnostic_are_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            log = root / "full.log"
            with log.open("w") as stream:
                code = run_command(
                    [sys.executable, "-c", "print('diagnostic'); raise SystemExit(7)"],
                    root,
                    stream,
                )
            self.assertEqual(code, 7)
            self.assertIn("diagnostic", log.read_text())

    def test_timeout_is_failure_and_process_is_reaped(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (root / "full.log").open("w") as stream:
                code = run_command(
                    [sys.executable, "-c", "import time; time.sleep(30)"],
                    root,
                    stream,
                    timeout=0.05,
                )
            self.assertEqual(code, 124)

    def test_missing_executable_is_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with (root / "full.log").open("w") as stream:
                self.assertEqual(
                    run_command([str(root / "missing")], root, stream), 127
                )
