#!/usr/bin/env python3
"""M 统一语音入口：本地 Whisper 转写，MiMo 配音。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import mimo_audio


def parser():
    root = mimo_audio.parser()
    root.description = __doc__
    commands = next(action for action in root._actions if action.dest == 'mode')
    p = commands.add_parser('asr', help='本地 Whisper 转写；不使用 MiMo、不上传')
    p.add_argument('--audio', required=True, type=Path, help='本地音频或视频')
    p.add_argument('--output-dir', required=True, type=Path, help='不存在的新目录；输出 TXT/SRT/VTT/TSV/JSON')
    p.add_argument('--model-file', type=Path, default=Path.home() / '.cache/whisper/base.pt', help='已有本地 Whisper .pt 模型；不下载')
    p.add_argument('--language', choices=('auto', 'zh', 'en'), default='auto')
    p.add_argument('--timeout', type=mimo_audio.positive_timeout, default=3600)
    p.add_argument('--dry-run', action='store_true', help='仅检查依赖和路径，不加载模型、不转写')
    return root


def run_asr(args):
    executable = shutil.which('whisper')
    if not executable or not shutil.which('ffmpeg'):
        raise ValueError('需要已有 Whisper CLI 和 FFmpeg；未安装或下载任何内容。')
    source = args.audio.expanduser().resolve()
    model = args.model_file.expanduser().resolve()
    output = args.output_dir.expanduser().absolute()
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError('本地输入文件不存在或为空。')
    if not model.is_file() or model.stat().st_size == 0:
        raise ValueError('本地模型不存在或为空；请指定已有模型，不自动下载。')
    if output.exists() or output.is_symlink():
        raise ValueError('输出目录已存在；请选择新目录，避免覆盖。')
    summary = {'provider': 'local-whisper', 'model_file': str(model), 'device': 'cpu',
               'language': args.language, 'word_timestamps': True, 'output_dir': str(output)}
    if args.dry_run:
        return {'dry_run': True, **summary}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.m-whisper-', dir=output.parent) as temp:
        command = [executable, str(source), '--model', str(model), '--device', 'cpu',
                   '--fp16', 'False', '--task', 'transcribe', '--word_timestamps', 'True',
                   '--output_format', 'all', '--output_dir', temp, '--verbose', 'False']
        if args.language != 'auto':
            command += ['--language', args.language]
        # No API credentials are needed by this local subprocess.
        env = {k: v for k, v in os.environ.items() if k not in ('MIMO_API_KEY', 'OPENAI_API_KEY')}
        try:
            result = subprocess.run(command, env=env, capture_output=True, text=True, timeout=args.timeout)
        except subprocess.TimeoutExpired:
            raise ValueError('本地 Whisper 转写超时；未交付输出，可检查素材长度或调整 --timeout。') from None
        files = [Path(temp) / (source.stem + '.' + ext) for ext in ('txt', 'srt', 'vtt', 'tsv', 'json')]
        # Whisper CLI may catch an internal exception and still exit zero.
        if result.returncode != 0 or not all(path.is_file() for path in files):
            raise ValueError('本地 Whisper 未生成完整输出；检查媒体、模型和本地运行环境。')
        transcript = json.loads(files[-1].read_text(encoding='utf-8'))
        if not isinstance(transcript.get('text'), str) or not isinstance(transcript.get('segments'), list):
            raise ValueError('Whisper JSON 结构不完整；未交付输出。')
        output.mkdir()  # Exclusive reservation: never replace an existing destination.
        for path in files:
            with (output / path.name).open('xb') as target:
                target.write(path.read_bytes())
    return {**summary, 'files': [str(output / path.name) for path in files],
            'text_characters': len(transcript['text']), 'segments': len(transcript['segments']),
            'empty_transcript': not transcript['text'].strip()}


def main(argv=None):
    args = parser().parse_args(argv)
    if args.mode != 'asr':
        return mimo_audio.entrypoint(argv)
    try:
        print(json.dumps(run_asr(args), ensure_ascii=False))
        return 0
    except (ValueError, OSError) as exc:
        print('本地 ASR 失败：' + str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
