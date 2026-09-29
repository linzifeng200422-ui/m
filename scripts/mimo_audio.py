#!/usr/bin/env python3
"""MiMo: preset TTS, voice cloning and voice design."""
import argparse
import base64
import io
import json
import math
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import wave

BASE_URL = "https://token-plan-cn.xiaomimimo.com/v1"
MODELS = {"tts": "mimo-v2.5-tts",
          "voiceclone": "mimo-v2.5-tts-voiceclone", "voicedesign": "mimo-v2.5-tts-voicedesign"}
VOICES = {
    "mimo_default": {"language": "集群默认", "gender": "中国集群默认为冰糖"},
    "冰糖": {"language": "zh", "gender": "female"},
    "茉莉": {"language": "zh", "gender": "female"},
    "苏打": {"language": "zh", "gender": "male"},
    "白桦": {"language": "zh", "gender": "male"},
    "Mia": {"language": "en", "gender": "female"},
    "Chloe": {"language": "en", "gender": "female"},
    "Milo": {"language": "en", "gender": "male"},
    "Dean": {"language": "en", "gender": "male"},
}
MAX_BASE64_BYTES = 10_000_000
MAX_AUDIO_BYTES = 3 * (MAX_BASE64_BYTES // 4)


class MiMoError(ValueError):
    """Locally authored errors safe to show without private payloads."""


def load_api_key():
    key = os.environ.get("MIMO_API_KEY", "").strip()
    if key:
        return key
    credential = Path.home() / ".config" / "mimotts" / "api-key"
    if credential.is_symlink():
        raise MiMoError("凭据文件不能是符号链接。")
    try:
        descriptor = os.open(credential, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            info = os.fstat(handle.fileno())
            if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
                    or info.st_mode & 0o077):
                raise MiMoError("凭据须由当前用户所有且禁止其他用户访问（建议权限 600）。")
            key = handle.read().strip()
    except FileNotFoundError:
        raise MiMoError("未找到密钥：配置 MIMO_API_KEY 或 ~/.config/mimotts/api-key。") from None
    if not key:
        raise MiMoError("MiMo 凭据为空。")
    return key


def wav_info(data):
    try:
        with wave.open(io.BytesIO(data), "rb") as wav:
            frames = wav.getnframes()
            if (frames <= 0 or wav.getframerate() <= 0
                    or len(wav.readframes(frames)) != frames * wav.getnchannels() * wav.getsampwidth()):
                raise MiMoError("WAV 为空或已截断。")
            return {"duration_seconds": round(frames / wav.getframerate(), 6),
                    "sample_rate": wav.getframerate(), "channels": wav.getnchannels()}
    except (wave.Error, EOFError):
        raise MiMoError("需要可读的 PCM WAV；其他编码请先用本地 FFmpeg 转换。") from None


def audio_data_uri(data, mime):
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise MiMoError("音频为空或超限：Base64 编码后不得超过 10 MB；请先压缩或选取片段。")
    return "data:" + mime + ";base64," + base64.b64encode(data).decode("ascii")


def read_audio(path):
    """Read a local PCM WAV or inspect an MP3; never download a URL."""
    if path.suffix.lower() not in (".wav", ".mp3"):
        raise MiMoError("输入仅接受 WAV/MP3；视频、M4A 等请先用本地 FFmpeg 提取或转换。")
    if not path.is_file():
        raise MiMoError("输入音频不存在或不是普通文件。")
    if path.stat().st_size > MAX_AUDIO_BYTES:
        raise MiMoError("音频超限：Base64 编码后不得超过 10 MB；请先压缩或选取片段。")
    data = path.read_bytes()
    if path.suffix.lower() == ".wav":
        info, mime = wav_info(data), "audio/wav"
    else:
        probe = shutil.which("ffprobe")
        if not probe:
            raise MiMoError("检查 MP3 需要本地 ffprobe；可改用 PCM WAV。")
        try:
            result = subprocess.run(
                [probe, "-v", "error", "-select_streams", "a:0", "-show_entries",
                 "stream=codec_name,sample_rate,channels:format=duration", "-of", "json", str(path.resolve())],
                capture_output=True, text=True, timeout=30, check=True)
            metadata = json.loads(result.stdout)
            stream = metadata["streams"][0]
            duration = float(metadata["format"]["duration"])
            rate, channels = int(stream["sample_rate"]), int(stream["channels"])
            if stream["codec_name"] != "mp3" or not math.isfinite(duration) or min(duration, rate, channels) <= 0:
                raise ValueError
            info = {"duration_seconds": round(duration, 6), "sample_rate": rate, "channels": channels}
        except (subprocess.SubprocessError, ValueError, KeyError, IndexError):
            raise MiMoError("MP3 检查失败；文件可能损坏或只是改了扩展名。") from None
        mime = "audio/mpeg"
    return audio_data_uri(data, mime), {"format": path.suffix.lower()[1:], **info}


def build_speech_request(mode, text, instruction="", *, voice="mimo_default",
                         reference_uri=None, description=""):
    if mode not in ("tts", "voiceclone", "voicedesign"):
        raise MiMoError("未知语音合成模式。")
    if not text.strip():
        raise MiMoError("待朗读文案不能为空。")
    audio = {"format": "wav"}
    if mode == "tts":
        if voice not in VOICES:
            raise MiMoError("未知预置音色；使用 voices 命令查看列表。")
        audio["voice"] = voice
    elif mode == "voiceclone":
        if not reference_uri:
            raise MiMoError("音色克隆需要参考音频。")
        audio["voice"] = reference_uri
    else:
        if not description.strip():
            raise MiMoError("音色设计需要具体的声音描述。")
        instruction = description + ("\n\n表达要求：" + instruction if instruction else "")
        # The website's True example can rewrite the user's narration.
        audio["optimize_text_preview"] = False
    return {"model": MODELS[mode],
            "messages": [{"role": "user", "content": instruction},
                         {"role": "assistant", "content": text}],
            "audio": audio}


def read_option(args, name):
    file = getattr(args, name + "_file", None)
    return file.read_text(encoding="utf-8") if file else getattr(args, name, "")


def positive_timeout(value):
    try:
        number = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError("timeout 必须是正数。") from None
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("timeout 必须是有限正数。")
    return number


def parser():
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="mode", required=True)
    commands.add_parser("voices", help="离线列出预置音色，不调用 API")
    for mode, help_text in [("tts", "预置音色配音"),
                            ("voiceclone", "参考音频克隆配音"), ("voicedesign", "文字描述设计声音")]:
        p = commands.add_parser(mode, help=help_text)
        p.add_argument("--output", required=True, type=Path, help="新输出路径；须为 .wav")
        p.add_argument("--dry-run", action="store_true", help="离线检查；不读取密钥、不请求接口、不写输出")
        p.add_argument("--timeout", type=positive_timeout, default=300.0, help="请求超时秒数（默认 300）")
        p.add_argument("--text-file", required=True, type=Path, help="完整待朗读文案，UTF-8")
        group = p.add_mutually_exclusive_group()
        group.add_argument("--instruction", default="", help="语气、语速、情绪等自然语言指令")
        group.add_argument("--instruction-file", type=Path, help="从 UTF-8 文件读取风格指令")
        if mode == "tts":
            p.add_argument("--voice", choices=tuple(VOICES), default="mimo_default")
        if mode == "voiceclone":
            p.add_argument("--reference-audio", required=True, type=Path, help="本地 WAV/MP3")
        if mode == "voicedesign":
            group = p.add_mutually_exclusive_group(required=True)
            group.add_argument("--description", help="声音描述：年龄、音色、口音、气质等")
            group.add_argument("--description-file", type=Path, help="从 UTF-8 文件读取声音描述")
    return root


def prepare(args):
    suffix = ".wav"
    if args.output.suffix.lower() != suffix:
        raise MiMoError("当前模式的输出文件扩展名须为 " + suffix + "。")
    if args.output.exists() or args.output.is_symlink():
        raise MiMoError("输出路径已存在；请选择新路径，避免覆盖原文件。")
    summary = {"mode": args.mode, "base_url": BASE_URL, "model": MODELS[args.mode]}
    text = args.text_file.read_text(encoding="utf-8")
    options = {"voice": getattr(args, "voice", "mimo_default")}
    if args.mode == "voiceclone":
        options["reference_uri"], summary["reference_audio"] = read_audio(args.reference_audio)
    if args.mode == "voicedesign":
        options["description"] = read_option(args, "description")
        summary["optimize_text_preview"] = False
    if args.mode == "tts":
        summary["voice"] = args.voice
    request = build_speech_request(args.mode, text, read_option(args, "instruction"), **options)
    summary["text_characters"] = len(text)
    summary["roles"] = [message["role"] for message in request["messages"]]
    return request, summary


def get_field(obj, name, default=None):
    return obj.get(name, default) if isinstance(obj, dict) else getattr(obj, name, default)


def decode_result(completion, mode):
    choices = get_field(completion, "choices", [])
    if not choices:
        raise MiMoError("服务返回空结果；未保存输出，请先检查服务状态。")
    choice = choices[0]
    if get_field(choice, "finish_reason") not in (None, "stop"):
        raise MiMoError("服务未正常完成（可能达到长度限制）；未把截断结果保存为成品。")
    message = get_field(choice, "message")
    encoded = get_field(get_field(message, "audio"), "data")
    if not isinstance(encoded, str) or not encoded:
        raise MiMoError("服务未返回音频数据。")
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError:
        raise MiMoError("服务返回的音频 Base64 无效。") from None
    return data, wav_info(data)


def run(args, client_factory=None):
    if args.mode == "voices":
        return {"voices": [{"id": key, **value} for key, value in VOICES.items()]}
    request, summary = prepare(args)
    if args.dry_run:
        return {"dry_run": True, **summary}
    if client_factory is None:
        from openai import OpenAI
        client_factory = OpenAI
    key = load_api_key()
    # Reserve a new writable output before a potentially billable request.
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("xb") as output:
        original = os.fstat(output.fileno())
        try:
            with client_factory(api_key=key, base_url=BASE_URL, max_retries=0,
                                timeout=args.timeout) as client:
                completion = client.chat.completions.create(**request)
            data, info = decode_result(completion, args.mode)
            output.write(data)
            output.flush()
        except BaseException:
            # Remove only our own failed placeholder, never a replacement file.
            current = args.output.lstat() if args.output.exists() else None
            if current and (current.st_dev, current.st_ino) == (original.st_dev, original.st_ino):
                args.output.unlink()
            raise
    return {"output": str(args.output.resolve()), **summary, **info}


def main(argv=None):
    print(json.dumps(run(parser().parse_args(argv)), ensure_ascii=False))


def entrypoint(argv=None):
    try:
        main(argv)
    except MiMoError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:
        # SDK error bodies can contain private payloads, so never print them.
        category = type(exc).__name__
        hints = {
            "AuthenticationError": "认证失败；检查当前 Token Plan 凭据。",
            "PermissionDeniedError": "服务拒绝访问；检查账户权限。",
            "RateLimitError": "额度或速率受限；未自动重试。",
            "APITimeoutError": "请求超时，服务是否已处理不确定；不要直接重复提交。",
            "APIConnectionError": "连接中断，服务是否已处理不确定；不要直接重复提交。",
            "BadRequestError": "服务拒绝参数；核对当前模式、输入长度及格式。",
            "ModuleNotFoundError": "缺少依赖；请使用已安装 openai 的 Python 环境。",
        }
        print("MiMo failed: " + category + "; " + hints.get(category,
              "检查本地路径、权限及服务状态后再决定是否重试。"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(entrypoint())
