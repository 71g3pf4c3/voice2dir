import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def run_cli(args):
    return subprocess.run(
        [sys.executable, "-m", "voice2dir.cli", *args],
        capture_output=True, text=True, cwd=REPO,
    )


class CliBuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name) / "tree"

    def tearDown(self):
        self.tmp.cleanup()

    def test_build_from_file(self):
        transcript = Path(self.tmp.name) / "t.txt"
        transcript.write_text("файл привет\nпривет мир\nконец файла\n", encoding="utf-8")
        result = run_cli(["build", str(transcript), str(self.out)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.out / "привет").read_text(encoding="utf-8"), "привет мир\n")

    def test_build_from_stdin(self):
        result = subprocess.run(
            [sys.executable, "-m", "voice2dir.cli", "build", "-", str(self.out)],
            input="каталог а\nфайл б\nx\nконец файла\n",
            capture_output=True, text=True, cwd=REPO,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.out / "а" / "б").is_file())

    def test_json_mode(self):
        transcript = Path(self.tmp.name) / "t.txt"
        transcript.write_text("файл а\nб\nконец файла\n", encoding="utf-8")
        result = run_cli(["build", "--json", str(transcript)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"а": "б\\n"', result.stdout)
        self.assertFalse(self.out.exists())

    def test_dry_run(self):
        transcript = Path(self.tmp.name) / "t.txt"
        transcript.write_text("каталог а\nфайл б\nx\nконец файла\n", encoding="utf-8")
        result = run_cli(["build", "--dry-run", str(transcript), str(self.out)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("создать:", result.stdout)
        self.assertFalse(self.out.exists())

    def test_dsl_error_exit_1(self):
        transcript = Path(self.tmp.name) / "t.txt"
        transcript.write_text("мусорная строка\n", encoding="utf-8")
        result = run_cli(["build", str(transcript), str(self.out)])
        self.assertEqual(result.returncode, 1)
        self.assertIn("не распознана", result.stderr)

    def test_usage_error_exit_2(self):
        result = run_cli(["build"])
        self.assertEqual(result.returncode, 2)

    def test_missing_file_exit_1(self):
        result = run_cli(["build", str(Path(self.tmp.name) / "нет.txt"), str(self.out)])
        self.assertEqual(result.returncode, 1)

    def test_lenient_mode(self):
        transcript = Path(self.tmp.name) / "t.txt"
        transcript.write_text(
            "шум\nфайл а\nx\nконец файла\n", encoding="utf-8"
        )
        result = run_cli(["build", "--lenient", str(transcript), str(self.out)])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.out / "а").read_text(encoding="utf-8"), "x\n")

    def test_build_json_mode(self):
        result = subprocess.run(
            [sys.executable, "-m", "voice2dir.cli",
             "build", "--mode", "json", "-", str(self.out)],
            input=("фигурная скобка кавычка а кавычка двоеточие "
                   "кавычка бэ кавычка закрывающая фигурная скобка"),
            capture_output=True, text=True, cwd=REPO,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.out / "а").read_text(encoding="utf-8"), "бэ")

    def test_build_json_mode_error_exit_1(self):
        result = subprocess.run(
            [sys.executable, "-m", "voice2dir.cli",
             "build", "--mode", "json", "-", str(self.out)],
            input="фигурная скобка",
            capture_output=True, text=True, cwd=REPO,
        )
        self.assertEqual(result.returncode, 1)


if __name__ == "__main__":
    unittest.main()
