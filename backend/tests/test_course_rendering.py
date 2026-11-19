import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


class CourseRenderingTest(unittest.TestCase):
    def test_sadtalker_chunking_and_missing_output(self):
        # Keep database imports isolated from the workflow test's data directory.
        with TemporaryDirectory() as directory:
            env = dict(os.environ, DIANOIA_DATA_DIR=directory, DIANOIA_DATABASE_URL="sqlite:///:memory:")
            script = r"""
import wave
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.course_media import CourseMediaError, audio_seconds
from app.course_worker import animate_avatar

with TemporaryDirectory() as temporary:
    root = Path(temporary)
    page = root / 'page-1'
    page.mkdir()
    audio = page / 'speech.wav'
    with wave.open(str(audio), 'wb') as target:
        target.setparams((1, 2, 16000, 0, 'NONE', 'not compressed'))
        target.writeframes(b'\x00\x00' * 200000)
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        if '--result_dir' in args:
            folder = Path(args[args.index('--result_dir') + 1])
            (folder / 'finished.mp4').write_bytes(b'test-video')
        else:
            (page / 'avatar.mp4').write_bytes(b'joined-video')
    stages = []
    with patch('app.course_worker.sadtalker_command', return_value=(root, ['renderer'])), patch('app.course_worker.run', side_effect=run):
        output = animate_avatar(page, audio, lambda: None, lambda index, total: stages.append((index, total)))
        assert output.read_bytes() == b'joined-video'
        assert stages == [(1, 2), (2, 2)], stages
        lengths = [audio_seconds(page / ('talk-' + str(index)) / 'speech.wav') for index in (1, 2)]
        assert lengths == [11.0, 1.5], lengths
        assert len(calls) == 3

    other = root / 'page-2'
    other.mkdir()
    with patch('app.course_worker.sadtalker_command', return_value=(root, ['renderer'])), patch('app.course_worker.run'):
        try:
            animate_avatar(other, audio, lambda: None, lambda *args: None)
        except CourseMediaError:
            pass
        else:
            raise AssertionError('An empty renderer result must fail')
"""
            result = subprocess.run([sys.executable, "-c", script], cwd=Path(__file__).parents[1],
                                    env=env, capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
