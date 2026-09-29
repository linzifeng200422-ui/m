"""Local ASR routing/failure tests; no model download or service calls."""
import io
import json
from pathlib import Path
import tempfile
import unittest
from contextlib import redirect_stdout
from unittest import mock
import m_audio


class LocalASRTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.audio = self.root / 'input.wav'
        self.audio.write_bytes(b'fake-test-audio')
        self.model = self.root / 'base.pt'
        self.model.write_bytes(b'fake-test-model')
        self.argv = ['asr', '--audio', str(self.audio), '--model-file', str(self.model),
                     '--output-dir', str(self.root / 'out')]
        self.which = mock.patch.object(m_audio.shutil, 'which', return_value='/mock/bin/tool')
        self.which.start()
        self.addCleanup(self.which.stop)

    def test_dry_run_does_not_read_credentials_or_launch(self):
        with mock.patch.object(m_audio.mimo_audio, 'load_api_key', side_effect=AssertionError), \
             mock.patch.object(m_audio.subprocess, 'run', side_effect=AssertionError), redirect_stdout(io.StringIO()):
            self.assertEqual(m_audio.main(self.argv + ['--dry-run']), 0)
        self.assertFalse((self.root / 'out').exists())

    def test_missing_model_and_existing_output_stop_before_launch(self):
        args = m_audio.parser().parse_args(self.argv)
        with mock.patch.object(m_audio.subprocess, 'run', side_effect=AssertionError):
            (self.root / 'out').mkdir()
            with self.assertRaises(ValueError): m_audio.run_asr(args)
            (self.root / 'out').rmdir()
            self.model.unlink()
            with self.assertRaises(ValueError): m_audio.run_asr(args)

    def test_success_routes_local_and_publishes_files(self):
        def fake_run(command, **kw):
            self.assertEqual(command[command.index('--model') + 1], str(self.model.resolve()))
            self.assertEqual(command[command.index('--device') + 1], 'cpu')
            self.assertNotIn('MIMO_API_KEY', kw['env'])
            directory = Path(command[command.index('--output_dir') + 1])
            for ext in ('txt', 'srt', 'vtt', 'tsv'):
                (directory / ('input.' + ext)).write_text('test')
            (directory / 'input.json').write_text(json.dumps({'text': 'test', 'segments': []}))
            return mock.Mock(returncode=0)
        with mock.patch.object(m_audio.subprocess, 'run', side_effect=fake_run), \
             mock.patch.object(m_audio.mimo_audio, 'load_api_key', side_effect=AssertionError):
            result = m_audio.run_asr(m_audio.parser().parse_args(self.argv))
        self.assertEqual(len(result['files']), 5)
        self.assertTrue(all(Path(f).is_file() for f in result['files']))

    def test_zero_exit_without_outputs_is_failure(self):
        with mock.patch.object(m_audio.subprocess, 'run', return_value=mock.Mock(returncode=0)):
            with self.assertRaises(ValueError):
                m_audio.run_asr(m_audio.parser().parse_args(self.argv))
        self.assertFalse((self.root / 'out').exists())

    def test_synthesis_delegates_to_existing_mimo_entry(self):
        argv = ['tts', '--text-file', 'script.txt', '--output', 'voice.wav', '--dry-run']
        with mock.patch.object(m_audio.mimo_audio, 'entrypoint', return_value=0) as delegate:
            self.assertEqual(m_audio.main(argv), 0)
            delegate.assert_called_once_with(argv)


if __name__ == '__main__': unittest.main(verbosity=2)
