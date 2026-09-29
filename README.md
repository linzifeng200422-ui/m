# m · 统一语音工具

`m` 是一个简洁高效的统一语音命令行与 Agent 工具，整合了本地离线 Whisper ASR 语音识别与 MiMo（小米配音）云端语音合成能力。

项目仓库：[linzifeng200422-ui/m](https://github.com/linzifeng200422-ui/m)

## 功能一览

| 功能模式 | 子命令 | 核心能力 | 输入 → 输出 | 网络与凭据 |
| --- | --- | --- | --- | --- |
| **本地 ASR** | `asr` | 基于本地 Whisper 进行音视频识别，生成多格式字幕与词级时间戳 | 本地音视频文件 → TXT/SRT/VTT/TSV/JSON | **纯本地离线**，不调用云端、不读密钥、不上传素材 |
| **预置音色 TTS** | `tts` | 使用 MiMo 官方预置音色朗读文案 | UTF-8 文案 + 预置音色名（如“苏打”、“冰糖”） → WAV | 调用 MiMo API，需凭据 |
| **音色克隆** | `voiceclone` | 根据给定的参考音频片段复刻声线并朗读新文案 | UTF-8 文案 + 参考音频（WAV/MP3，Base64 < 10 MB） → WAV | 调用 MiMo API，需凭据，单次任务授权上传 |
| **声音设计** | `voicedesign` | 根据自然语言特征描述（年龄、性别、口音、气质等）创造声线朗读 | UTF-8 文案 + 声音自然语言描述 → WAV | 调用 MiMo API，需凭据，原稿不改写 |

## 运行前提

- **操作系统**：macOS 或 Linux
- **Python**：Python 3.10+
- **系统依赖**（用于本地 ASR 及音频处理，需在系统 `PATH` 中可用）：
  - `whisper`：本地 Whisper 命令行工具
  - `ffmpeg`：本地音视频解码与转换工具
  - `ffprobe`：音频元数据检查工具（使用 MP3 参考音频时必需；使用标准 PCM WAV 则不依赖）
  > 注：本项目不自动安装 `whisper` / `ffmpeg`，亦不自动下载模型。本地 ASR 默认使用已存在的 `~/.cache/whisper/base.pt` 模型，也可通过 `--model-file` 参数显式指定其他本地现有模型路径。

## 安装与依赖配置

先获取项目，再在项目根目录下创建 Python 虚拟环境并安装运行依赖：

```bash
git clone https://github.com/linzifeng200422-ui/m.git
cd m

# 1. 创建并激活虚拟环境
python3 -m venv .venv
source .venv/bin/activate

# 2. 安装必要依赖（固定 openai 与 httpx 版本）
pip install -r requirements.txt
```

## MiMo 凭据与安全规范

MiMo 云端合成接口固定使用 Token Plan 服务端点：
`https://token-plan-cn.xiaomimimo.com/v1`

### 凭据配置方式

程序按以下顺序读取 API Key：
1. **环境变量**：优先读取 `MIMO_API_KEY`。
2. **本地文件**：若环境变量未设置，读取本机配置文件 `~/.config/mimotts/api-key`。

**安全配置建议：**
若使用本地文件存放凭据，建议设置严格的文件权限（仅当前用户可读写），避免凭据泄露，且**不能为符号链接**：
```bash
mkdir -p ~/.config/mimotts
chmod 700 ~/.config/mimotts
touch ~/.config/mimotts/api-key
chmod 600 ~/.config/mimotts/api-key
# 将您的有效 API 密钥写入该文件（仅包含密钥单行文本）
```

> **重要提示：**
> - **代码不会自动读取 `.env` 文件**。请勿将密钥写入 `.env` 并期望程序自动加载；请通过导出环境变量或写入 `~/.config/mimotts/api-key` 的方式配置。
> - 严禁将 API Key 提交到 Git 仓库，或直接拼入公共终端命令历史中。
> - 命令行接口不接收任何密钥参数。

### 授权与隐私约定

1. **本地 ASR**：完全在本地离线运行，绝不读取 API 密钥，绝不上传任何音频或数据。
2. **MiMo 云端合成**：每次任务授权覆盖具体音频和用途。用户明确要求由 MiMo 处理本次指定的音频（例如音色克隆的参考声音）即代表授予该次任务上传 MiMo 服务的权限，已获得授权则不重复确认。单纯询问功能、查看帮助或执行 `--dry-run` 离线检查绝不会触发网络请求或上传音频。此授权绝不扩大至任意收集其他私人音频或转交第三方服务。

## CLI 使用示例

在仓库根目录下，通过 `python3 scripts/m_audio.py` 调用所有功能：

### 1. 查看帮助与预置音色

```bash
# 查看所有命令选项
python3 scripts/m_audio.py --help

# 离线列出 MiMo 支持的所有预置音色（无需密钥、不请求网络）
python3 scripts/m_audio.py voices
```

### 2. 本地 Whisper 语音转写 (ASR)

转写本地音视频文件，生成 TXT、SRT、VTT、TSV、JSON 格式结果（含逐词时间戳）：

```bash
# 离线检查参数与路径有效性（--dry-run）
python3 scripts/m_audio.py asr \
  --audio "/绝对路径/输入视频.mp4" \
  --output-dir "/绝对路径/新转写目录" \
  --language zh \
  --dry-run

# 正式执行转写（输出目录必须为尚不存在的新目录）
python3 scripts/m_audio.py asr \
  --audio "/绝对路径/输入视频.mp4" \
  --output-dir "/绝对路径/新转写目录" \
  --language zh
```

### 3. 预置音色配音 (TTS)

```bash
# 先使用 --dry-run 校验文本与参数
python3 scripts/m_audio.py tts \
  --text-file "/绝对路径/文案.txt" \
  --voice 苏打 \
  --instruction "自然聊天的语气，语速适中" \
  --output "/绝对路径/配音.wav" \
  --dry-run

# 去掉 --dry-run 正式执行
python3 scripts/m_audio.py tts \
  --text-file "/绝对路径/文案.txt" \
  --voice 苏打 \
  --instruction "自然聊天的语气，语速适中" \
  --output "/绝对路径/配音.wav"
```

### 4. 参考音频音色克隆 (VoiceClone)

```bash
# 离线检查 PCM WAV/MP3；Base64 编码后不得超过 10 MB（原文件约 7.5 MB）
python3 scripts/m_audio.py voiceclone \
  --text-file "/绝对路径/新文案.txt" \
  --reference-audio "/绝对路径/参考声音.wav" \
  --instruction "保持原声特点，自然平稳" \
  --output "/绝对路径/克隆配音.wav" \
  --dry-run

# 正式生成
python3 scripts/m_audio.py voiceclone \
  --text-file "/绝对路径/新文案.txt" \
  --reference-audio "/绝对路径/参考声音.wav" \
  --instruction "保持原声特点，自然平稳" \
  --output "/绝对路径/克隆配音.wav"
```

> **兼容入口**：仓库内提供的 `python3 scripts/voiceclone.py` 为历史命令兼容入口，参数与 `m_audio.py voiceclone` 一致。

### 5. 自然语言声音设计 (VoiceDesign)

```bash
# 离线检查参数与消息结构
python3 scripts/m_audio.py voicedesign \
  --text-file "/绝对路径/文案.txt" \
  --description "四十岁左右男性，普通话，声音低沉微沙哑，富有亲和力" \
  --instruction "语速平缓，重点句略有停顿" \
  --output "/绝对路径/设计声音.wav" \
  --dry-run

# 正式生成
python3 scripts/m_audio.py voicedesign \
  --text-file "/绝对路径/文案.txt" \
  --description "四十岁左右男性，普通话，声音低沉微沙哑，富有亲和力" \
  --instruction "语速平缓，重点句略有停顿" \
  --output "/绝对路径/设计声音.wav"
```

## 合成行为核心约束

- **完整提交、一次合成**：待朗读文案全文放入 `assistant.content`，表达与音色要求放入 `user.content`。不擅自拆句拼接。
- **原稿保留**：VoiceDesign 模式下固定设置 `optimize_text_preview=false`，严格保护用户文案不被服务端自动改写。
- **防止误覆盖**：合成命令的 `--output` 必须是新文件路径；ASR 的 `--output-dir` 必须是新目录。已有输出不会被覆盖。
- **无静默重试**：单次请求超时默认为 300 秒（可通过 `--timeout` 调整）；SDK `max_retries` 设为 0。如遇网络异常或超时，需核对状态后明确处理，避免重复扣费。
- **安全过滤**：错误输出仅包含安全摘要与分类提示，绝不回显文案内容、音频 Base64 数据或原始错误响应体。

## 本地离线测试

项目自带完整的本地离线单元测试套件。测试使用合成音频、Mock 凭据与内存 HTTP 模拟，**不请求任何外部网络、不调用真实 MiMo API、不消耗账户配额**：

```bash
# 1. 运行本地 Whisper ASR 路由与校验测试
python3 scripts/test_m_audio.py

# 2. 运行 MiMo 合成离线模拟测试（涵盖全部三模式、格式校验与错误处理）
python3 scripts/test_mimo_audio.py
```

> **说明**：离线测试通过仅代表本地代码逻辑、协议构建和分支校验符合预期；由于未连接线上服务，**不能证明真实 Token Plan 服务的账户额度、线上可用性或合成音频的最终配音听感**。生成真实配音后请以实际试听为准。

## 作为 Codex Skill 安装（可选）

如需将本工具作为 Agent Skill 使用，可将本仓库放置或链接至 Codex Skills 目录下：

```bash
# 示例：目标目录（请根据实际环境使用，注意不要覆盖已有同名目录）
SKILL_DIR="${CODEX_HOME:-$HOME/.codex}/skills/m"
```
详细用法与自然语言匹配规则请参阅 [SKILL.md](SKILL.md) 与 [references/usage.md](references/usage.md)。
