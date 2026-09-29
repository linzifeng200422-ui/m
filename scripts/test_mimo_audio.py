#!/usr/bin/env python3
"""Offline behavior tests. No real keys, audio uploads or MiMo requests."""
import base64
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import wave

import httpx
import openai
from openai import OpenAI as RealOpenAI
import mimo_audio as mimo


def make_wav(rate=16000, channels=1):
    stream = io.BytesIO()
    with wave.open(stream, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * (rate // 10) * channels)
    return stream.getvalue()


class MiMoBehaviorTests(unittest.TestCase):
    def setUp(self):
        work = Path.cwd() / "work"
        work.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="mimo-offline-test-", dir=work)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.text = "这是完整的测试文案。\n[轻笑]第二句也要保留。"
        self.script = self.root / "script.txt"
        self.script.write_text(self.text, encoding="utf-8")
        self.audio = self.root / "reference.wav"
        self.audio.write_bytes(make_wav())
        self.generated = make_wav(22050, 2)
        self.env = mock.patch.dict(os.environ, {"MIMO_API_KEY": "tp-offline-test-only"})
        self.env.start()
        self.addCleanup(self.env.stop)

    def command(self, mode, *extra):
        output = self.root / (mode + ".wav")
        argv = [mode, "--output", str(output)]
        argv += ["--text-file", str(self.script), "--instruction", "自然讲述"]
        if mode == "tts":
            argv += ["--voice", "苏打"]
        elif mode == "voiceclone":
            argv += ["--reference-audio", str(self.audio)]
        else:
            argv += ["--description", "中年男声，低沉略沙哑"]
        return argv + list(extra)

    def response(self, mode, finish="stop"):
        message = {"role": "assistant", "content": None,
                   "audio": {"data": base64.b64encode(self.generated).decode(),
                             "id": "audio-offline", "expires_at": 0, "transcript": self.text}}
        return {"id": "offline", "object": "chat.completion", "created": 0,
                "model": mimo.MODELS[mode],
                "choices": [{"index": 0, "finish_reason": finish, "message": message}]}

    def factory(self, mode, seen, status=200, timeout=False, body=None):
        def handle(request):
            seen.append((str(request.url), json.loads(request.content)))
            self.assertEqual(request.headers["authorization"], "Bearer tp-offline-test-only")
            if timeout:
                raise httpx.ReadTimeout("PRIVATE_TEST_PAYLOAD", request=request)
            payload = self.response(mode) if body is None else body
            return httpx.Response(status, json=payload)

        def create(**kwargs):
            self.assertEqual(kwargs["base_url"], "https://token-plan-cn.xiaomimimo.com/v1")
            self.assertEqual(kwargs["max_retries"], 0)
            return RealOpenAI(**kwargs, http_client=httpx.Client(transport=httpx.MockTransport(handle)))
        return create

    def test_three_modes_wire_contract_and_files(self):
        for mode in mimo.MODELS:
            with self.subTest(mode=mode):
                seen = []
                args = mimo.parser().parse_args(self.command(mode))
                summary = mimo.run(args, self.factory(mode, seen))
                self.assertEqual(len(seen), 1)
                url, body = seen[0]
                self.assertEqual(url, "https://token-plan-cn.xiaomimimo.com/v1/chat/completions")
                self.assertEqual(body["model"], mimo.MODELS[mode])
                self.assertEqual(body["messages"][1], {"role": "assistant", "content": self.text})
                self.assertEqual(body["audio"]["format"], "wav")
                self.assertEqual(args.output.read_bytes(), self.generated)
                self.assertEqual((summary["sample_rate"], summary["channels"]), (22050, 2))
                if mode == "tts":
                    self.assertEqual(body["audio"]["voice"], "苏打")
                elif mode == "voiceclone":
                    uri = body["audio"]["voice"]
                    self.assertTrue(uri.startswith("data:audio/wav;base64,"))
                    self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), self.audio.read_bytes())
                else:
                    self.assertIs(body["audio"]["optimize_text_preview"], False)
                    self.assertNotIn("voice", body["audio"])
                    self.assertIn("低沉略沙哑", body["messages"][0]["content"])
                self.assertNotIn(self.text, json.dumps(summary, ensure_ascii=False))

    def test_removed_asr_command_is_rejected_before_credentials(self):
        with mock.patch.object(mimo, "load_api_key", side_effect=AssertionError("credential read")):
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                mimo.main(["asr", "--audio", str(self.audio), "--output", str(self.root / "out.txt")])
            self.assertEqual(error.exception.code, 2)

    def test_dry_run_never_reads_credentials_or_creates_output(self):
        with mock.patch.object(mimo, "load_api_key", side_effect=AssertionError("credential read")):
            client = mock.Mock(side_effect=AssertionError("network request"))
            for mode in mimo.MODELS:
                with self.subTest(mode=mode):
                    args = mimo.parser().parse_args(self.command(mode, "--dry-run"))
                    result = mimo.run(args, client)
                    self.assertTrue(result["dry_run"])
                    self.assertFalse(args.output.exists())
            self.assertEqual(len(mimo.run(mimo.parser().parse_args(["voices"]), client)["voices"]), 9)
            client.assert_not_called()

    def test_existing_output_prevents_request(self):
        args = mimo.parser().parse_args(self.command("tts"))
        args.output.write_bytes(b"KEEP ORIGINAL")
        client = mock.Mock()
        with self.assertRaises(mimo.MiMoError):
            mimo.run(args, client)
        self.assertEqual(args.output.read_bytes(), b"KEEP ORIGINAL")
        client.assert_not_called()

    def test_input_errors_do_not_read_key_or_call_api(self):
        cases = []
        blank = self.root / "blank.txt"
        blank.write_text(" \n")
        malformed = self.root / "broken.wav"
        malformed.write_bytes(self.audio.read_bytes()[:-12])
        over = self.root / "oversize.wav"
        with over.open("wb") as f:
            f.truncate(mimo.MAX_AUDIO_BYTES + 1)
        for field, value in [("reference_audio", malformed), ("reference_audio", over),
                             ("reference_audio", self.root / "missing.wav"),
                             ("output", self.root / "bad.mp3")]:
            args = mimo.parser().parse_args(self.command("voiceclone"))
            setattr(args, field, value)
            cases.append(args)
        args = mimo.parser().parse_args(self.command("tts"))
        args.text_file = blank
        cases.append(args)
        args = mimo.parser().parse_args(self.command("voicedesign"))
        args.description = " "
        cases.append(args)
        with mock.patch.object(mimo, "load_api_key", side_effect=AssertionError("credential read")):
            for args in cases:
                with self.subTest(mode=args.mode, audio=str(getattr(args, "audio", ""))):
                    with self.assertRaises(mimo.MiMoError):
                        mimo.run(args, mock.Mock(side_effect=AssertionError("network request")))

    def test_server_errors_make_one_attempt_and_remove_failed_output(self):
        for status in [401, 403, 429, 500]:
            with self.subTest(status=status):
                seen = []
                body = {"error": {"message": "PRIVATE_TEST_PAYLOAD", "type": "offline_error"}}
                factory = self.factory("tts", seen, status=status, body=body)
                stdout, stderr = io.StringIO(), io.StringIO()
                with mock.patch.object(openai, "OpenAI", factory), redirect_stdout(stdout), redirect_stderr(stderr):
                    self.assertEqual(mimo.entrypoint(self.command("tts")), 1)
                self.assertEqual(len(seen), 1)
                self.assertFalse((self.root / "tts.wav").exists())
                self.assertNotIn("PRIVATE_TEST_PAYLOAD", stdout.getvalue() + stderr.getvalue())
                self.assertNotIn("tp-offline-test-only", stdout.getvalue() + stderr.getvalue())

    def test_timeout_is_not_retried(self):
        seen = []
        args = mimo.parser().parse_args(self.command("tts", "--timeout", "1"))
        with self.assertRaises(openai.APITimeoutError):
            mimo.run(args, self.factory("tts", seen, timeout=True))
        self.assertEqual(len(seen), 1)
        self.assertFalse(args.output.exists())

    def test_invalid_or_incomplete_service_results_are_not_saved(self):
        empty = self.response("tts")
        empty["choices"][0]["message"]["audio"]["data"] = ""
        invalid_base64 = self.response("tts")
        invalid_base64["choices"][0]["message"]["audio"]["data"] = "!!invalid!!"
        invalid_wav = self.response("tts")
        invalid_wav["choices"][0]["message"]["audio"]["data"] = base64.b64encode(b"not a wav").decode()
        for mode, response in [("tts", empty), ("tts", self.response("tts", "length")),
                               ("tts", invalid_base64), ("tts", invalid_wav)]:
            with self.subTest(mode=mode, response=response["choices"][0]["finish_reason"]):
                seen = []
                args = mimo.parser().parse_args(self.command(mode))
                with self.assertRaises(mimo.MiMoError):
                    mimo.run(args, self.factory(mode, seen, body=response))
                self.assertEqual(len(seen), 1)
                self.assertFalse(args.output.exists())

    def test_instruction_and_description_files_preserve_text(self):
        description = self.root / "description.txt"
        description.write_text("青年女声，清晰温暖。\n普通话。", encoding="utf-8")
        instruction = self.root / "instruction.txt"
        instruction.write_text("自然\n不要播音腔", encoding="utf-8")
        args = mimo.parser().parse_args([
            "voicedesign", "--text-file", str(self.script), "--description-file", str(description),
            "--instruction-file", str(instruction), "--output", str(self.root / "design.wav")])
        request, _ = mimo.prepare(args)
        self.assertIn(description.read_text(), request["messages"][0]["content"])
        self.assertIn(instruction.read_text(), request["messages"][0]["content"])
        self.assertEqual(request["messages"][1]["content"], self.text)

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "MP3 check requires local FFmpeg")
    def test_real_mp3_and_renamed_fake_mp3(self):
        mp3 = self.root / "reference.mp3"
        subprocess.run([shutil.which("ffmpeg"), "-v", "error", "-nostdin", "-n", "-i", str(self.audio),
                        "-c:a", "libmp3lame", str(mp3)], check=True, capture_output=True, timeout=30)
        uri, info = mimo.read_audio(mp3)
        self.assertEqual(base64.b64decode(uri.split(",", 1)[1]), mp3.read_bytes())
        self.assertTrue(uri.startswith("data:audio/mpeg;base64,"))
        self.assertGreater(info["duration_seconds"], 0)
        for mode in ["voiceclone"]:
            args = mimo.parser().parse_args(self.command(mode, "--dry-run"))
            setattr(args, "reference_audio", mp3)
            self.assertTrue(mimo.run(args)["dry_run"])
        fake = self.root / "renamed.mp3"
        fake.write_bytes(self.audio.read_bytes())
        with self.assertRaises(mimo.MiMoError):
            mimo.read_audio(fake)

    def test_legacy_command_is_compatible(self):
        argv = self.command("voiceclone", "--dry-run")[1:]
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("voiceclone.py")), *argv],
                                text=True, capture_output=True, check=True, timeout=30)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["model"], mimo.MODELS["voiceclone"])
        self.assertEqual(summary["base_url"], mimo.BASE_URL)
        self.assertTrue(summary["dry_run"])
        self.assertFalse((self.root / "voiceclone.wav").exists())

    def test_credential_env_priority_and_safe_file_fallback(self):
        with mock.patch.object(mimo.Path, "home", return_value=self.root):
            self.assertEqual(mimo.load_api_key(), "tp-offline-test-only")
            cred = self.root / ".config" / "mimotts" / "api-key"
            cred.parent.mkdir(parents=True, mode=0o700)
            cred.write_text("tp-file-offline-only\n")
            cred.chmod(0o600)
            with mock.patch.dict(os.environ, {"MIMO_API_KEY": ""}):
                self.assertEqual(mimo.load_api_key(), "tp-file-offline-only")
                cred.chmod(0o644)
                with self.assertRaises(mimo.MiMoError):
                    mimo.load_api_key()
                cred.unlink()
                cred.symlink_to(self.script)
                with self.assertRaises(mimo.MiMoError):
                    mimo.load_api_key()
                cred.unlink()
                with self.assertRaises(mimo.MiMoError):
                    mimo.load_api_key()


if __name__ == "__main__":
    unittest.main(verbosity=2)
