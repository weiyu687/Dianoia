"""Integration coverage in a separate process to avoid sharing application globals."""
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest


class QuestionBanksTest(unittest.TestCase):
    def test_authoring_publication_and_generation(self):
        with TemporaryDirectory(prefix="dianoia-bank-test-") as directory:
            env = {**os.environ, "DIANOIA_DATA_DIR": directory,
                   "DIANOIA_DATABASE_URL": "sqlite:///" + Path(directory).as_posix() + "/test.db",
                   "DIANOIA_SEED_PASSWORD": "Synthetic-bank-test!", "DIANOIA_SECURE_COOKIE": "false",
                   "DIANOIA_MODEL_BASE_URL": "http://model.invalid/v1", "DIANOIA_MODEL_NAME": "question-bank-test",
                   "DIANOIA_MODEL_API_KEY": "test-only",
                   "PYTHONUTF8": "1", "PYTHONPATH": str(Path(__file__).resolve().parents[1])}
            result = subprocess.run([sys.executable, str(Path(__file__).with_name("question_bank_workflow.py"))],
                                    env=env, capture_output=True, text=True, encoding="utf-8", timeout=120)
            self.assertEqual(result.returncode, 0, result.stdout[-6000:] + result.stderr[-6000:])
