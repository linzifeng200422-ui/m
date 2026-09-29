# m · 统一语音工具使用说明

本工具技能名和显示名称均为 `m`，提供本地 Whisper 转写和 MiMo 语音合成能力。旧称 `mimotts` 继续识别。在仓库根目录下可直接通过 `python3 scripts/m_audio.py` 调用；若作为 Skill 安装，常见位置为 `${CODEX_HOME:-$HOME/.codex}/skills/m`。

## 日常怎么说

| 需求 | 示例 | 实际使用的功能 |
| --- | --- | --- |
| 录音或视频转写 | “用 M 把这段录音转成文字并生成字幕。” | 本地 Whisper |
| 普通配音 | “用自然的中文男声读这篇稿子。” | TTS 预置音色 |
| 克隆已有声音 | “用我给的这段参考声音，读这篇新稿子。” | VoiceClone |
| 创造新声音 | “设计一个中年男声，低沉、略沙哑，普通话，读这篇稿子。” | VoiceDesign |

你可以直接说“用 m 配音”“m 给这篇稿子配音”“用 m 克隆这段声音”，或使用 `$m`。转写使用本地 Whisper；配音任务使用 MiMo。视频中的旁白也适用；完整视频制作仍交给原来的剪辑流程。明确指定其他服务时，按你的选择执行。

**单次任务授权约定：**每次任务授权覆盖具体音频和用途。用户明确要求由 MiMo 处理本次指定的音频（如参考音频），即代表授权上传至 MiMo 完成本次任务，已获得授权则不重复确认。单纯询问功能、讨论方法或执行 `--dry-run` 离线检查不会发起上传、调用或生成。此约定不意味着主动收集其他私人音频，亦不授权转交第三方服务。

## 统一地址和运行环境

三种 MiMo 合成模式固定使用（本地 ASR 不用此地址）：

```text
https://token-plan-cn.xiaomimimo.com/v1
```

程序通过 OpenAI Python SDK 的 `chat.completions.create` 调用，实际请求路径为 `/v1/chat/completions`。不会自动切到普通按量 API 域名。

密钥优先读取环境变量 `MIMO_API_KEY`；为空时读取本机安全配置文件 `~/.config/mimotts/api-key`。不需要每次粘贴，命令行不接收密钥参数。凭据文件权限建议 600、目录 700，且不能为符号链接。**注意：代码不会自动读取 `.env` 文件**，请勿将密钥写入 `.env` 或提交至代码仓库。

依赖：Python 3.10+、`openai`、`httpx`；MP3 校验另需本地 `ffprobe`。优先使用现有环境。下面以仓库根目录为例定义脚本位置；示例中的 `/绝对路径/…` 需换成真实文件路径：

```bash
MIMO_TOOL="scripts/m_audio.py"
python3 "$MIMO_TOOL" --help
```

## 本地 Whisper：转写

复用系统 PATH 中已有的 `whisper` CLI 与本地模型缓存。M 的统一入口 `m_audio.py asr` 完全在本地运行，不调用 MiMo、不上传、不读 API 密钥。

```bash
python3 "$MIMO_TOOL" asr \
  --audio "/绝对路径/输入视频.mp4" \
  --output-dir "/绝对路径/新转写目录" \
  --language zh --dry-run
```

检查通过后去掉 `--dry-run` 执行。`--language` 支持 `auto`（默认）、`zh`、`en`；默认 CPU、FP32、已有 `~/.cache/whisper/base.pt`。可用 `--model-file /已有模型.pt` 切换现有本地 Whisper 模型，不传模型名称，不自动下载。`--timeout` 默认 3600 秒。缺依赖或模型直接报错，不回退 MiMo。

输出目录必须不存在；输出同名 TXT、SRT、VTT、TSV、JSON。JSON 保留 segments/words 时间戳；SRT 可作为字幕素材，导入由当前剪辑流程负责。中文词块不保证逐字，时间戳是估计值；不提供说话人分离。空文本标记 `empty_transcript=true`，不能称为有效语音识别结果。基础模型已缓存不代表对真实素材的准确率已验收，应按任务抽查原音频。

音视频通过已有 FFmpeg 在本地解码；不套用下面 MiMo 参考音频的格式或 10 MB 限制。长素材可耗时较久，跟进同一进程，不重复发起。脚本不打印原文，文字留在本地结果文件。

## 1. TTS：使用预置音色配音

**输入：**保存为 UTF-8 的完整文案。**输出：**`.wav`。

```bash
python3 "$MIMO_TOOL" tts \
  --text-file "/绝对路径/文案.txt" \
  --voice 苏打 \
  --instruction "自然聊天的语气，语速适中，减少播音腔" \
  --output "/绝对路径/配音.wav"
```

省略 `--voice` 时使用 `mimo_default`。中国集群的官方默认音色为“冰糖”；预置音色列表：

| Voice ID | 语言 | 声音 |
| --- | --- | --- |
| `mimo_default` | 随集群 | 中国集群默认“冰糖” |
| `冰糖`、`茉莉` | 中文 | 女声 |
| `苏打`、`白桦` | 中文 | 男声 |
| `Mia`、`Chloe` | 英文 | 女声 |
| `Milo`、`Dean` | 英文 | 男声 |

离线查看全部可选项：

```bash
python3 "$MIMO_TOOL" voices
```

音色名区分大小写，不需要参考音频或注册声线。风格描述通过 `user.content` 发送，全文在 `assistant.content`。

## 2. VoiceClone：参考音频克隆配音

**输入：**完整新文案 + 本次指定的参考 WAV/MP3。**输出：**`.wav`。

```bash
python3 "$MIMO_TOOL" voiceclone \
  --text-file "/绝对路径/新文案.txt" \
  --reference-audio "/绝对路径/参考声音.wav" \
  --instruction "保持原来的音色，自然平稳地讲述" \
  --output "/绝对路径/克隆配音.wav"
```

参考声音的 Base64 data URI 放入 `audio.voice`；不需要参考音频对应的逐字稿、预先训练或 voice ID。建议选择清晰、单人、背景音乐少的片段；声音质量和相似度仍需实际试听。

仓库内提供兼容入口 `scripts/voiceclone.py`（与 `m_audio.py voiceclone` 共用 `mimo_audio.py` 中的合成实现）：

```bash
python3 scripts/voiceclone.py \
  --text-file "/绝对路径/新文案.txt" \
  --reference-audio "/绝对路径/参考声音.wav" \
  --output "/绝对路径/克隆配音.wav"
```

## 3. VoiceDesign：通过描述设计声音

**输入：**完整文案 + 想要的声音描述。**输出：**以该声音朗读文案的 `.wav`。

```bash
python3 "$MIMO_TOOL" voicedesign \
  --text-file "/绝对路径/文案.txt" \
  --description "四十岁左右的男性，标准普通话，声音低沉略沙哑，沉稳、有亲近感" \
  --instruction "像向朋友解释事情，语速适中，重点处轻微放慢" \
  --output "/绝对路径/设计声音.wav"
```

描述可写年龄、性别、口音、音色质感、气质、节奏等，具体的 1—4 句话通常够用。`--description` 定义声音，`--instruction` 补充此次演绎方式；二者合并放在 `user.content`。

无需参考音频，不使用预置 voice ID。程序固定 `optimize_text_preview=false`，保留原稿文案。它直接生成音频，不注册永久 voice ID；以后要延续已选中的声音，可把该次生成结果选作 VoiceClone 参考，不能承诺每次重跑相同描述声线完全一致。

## 通用参数和表达控制

三种执行命令均支持：

| 参数 | 用途 |
| --- | --- |
| `--dry-run` | 仅检查输入、模型和消息结构；不读密钥、不联网、不写成品 |
| `--timeout 300` | 单次请求超时秒数，默认 300；不触发自动重试 |
| `--output` | 必填新路径；必须为 `.wav` |

三种配音命令均支持 `--instruction` 或 `--instruction-file`，两者只能选一个。长风格指令可用 UTF-8 文件；VoiceDesign 的描述同样支持 `--description-file` 替代 `--description`。

先在实际命令末尾加 `--dry-run` 验证，通过后去掉该参数执行一次。`voices` 和离线检查只返回结构摘要，生成命令返回文件位置、模型信息和音频规格；不会把文案、音频 Base64 或密钥打印到日志。

语速、情绪、重音、停顿通过自然语言表达，不使用未核实的数值型 `speed` 参数。需要句内表演时，可在准备好的文案中加入 `(平静)`、`[轻笑]`、`[叹气]` 等标签；程序原样传递，不自动改写或插入。唱歌标签仅属于预置 TTS，VoiceClone/VoiceDesign 不支持唱歌模式。

## 格式、长度和本地转换

- 克隆的输入为单份 WAV 或 MP3。Base64 编码后上限 10 MB，约相当于原文件 7.5 MB；脚本按十进制 MB 做保守检查。
- WAV 校验要求实际 PCM 内容；MP3 通过 ffprobe 检查实际编码和时长。不能通过改文件扩展名伪装格式。
- 本工具每次只提交一次完整请求。模型页面列出的上下文为 8K tokens，TTS 系列最大输出 8K tokens；这些不是“字数”或“分钟数”，脚本不伪装成精确 tokenizer 检查。过长任务先评估，不静默拆成多个付费调用。
- 合成结果保留服务返回的真实 WAV 采样率和声道；需要另一种规格时另存转换文件。

把视频、M4A 或其他编码的音频转换为供音色克隆使用的单声道 WAV（纯本地操作，`-n` 防覆盖）：

```bash
ffmpeg -nostdin -n -i "/绝对路径/输入视频.mp4" \
  -map 0:a:0 -vn -ac 1 -ar 24000 -c:a pcm_s16le "/绝对路径/参考声音.wav"
```

采样率是这里的本地选择，不是声称接口仅支持此值。选择参考片段时按实际任务使用，避免把无关的整段录音上传。

转换完成后再次 `--dry-run`，检查编码后大小。当前脚本提供完整响应保存，不提供实时播放、流式输出、自动分段、字幕对齐、降噪或混音。

## 错误时怎么处理

- **输入为空/格式不符/超限：**先修正或转换本地输入，未发送 API 请求。
- **输出已存在：**选新文件名；不会覆盖原文件，也不会因此先消耗一次请求。
- **缺依赖：**换到已有依赖的 Python 环境；确有缺失时在项目虚拟环境安装。
- **认证/权限失败：**检查当前 Token Plan 凭据及服务权限，不自动切换普通 API。
- **额度或频率限制：**核对套餐/速率状态；不自动反复重试。
- **超时/断连：**服务是否已经处理不确定，先核对状态，避免重复提交。
- **返回空白、损坏或未正常完成：**不作为有效成品保存；检查原因后决定下一步。

## 本地离线验证与官方依据

运行本地单元测试：

```bash
# 本地 ASR 路由测试
python3 scripts/test_m_audio.py

# MiMo 合成离线模拟测试
python3 scripts/test_mimo_audio.py
```

测试使用本地合成音频、假密钥和内存 HTTP 模拟响应，覆盖三模式的实际 SDK 请求与保存路径；**不上传素材、不调用真实 MiMo，不证明账户额度、线上可用性或配音听感**。真实配音生成后还需人工试听。

官方资料与接口依据（地址固定使用 Token Plan 配置；模型结构依照官方文档）：

- [TTS、VoiceClone、VoiceDesign 使用指南](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5)
- [Token Plan 接入及地址](https://mimo.mi.com/docs/zh-CN/tokenplan/Token%20Plan/quick-access)
- [TTS 模型规格](https://mimo.mi.com/models/zh-CN/mimo-v2.5-tts)

套餐适用范围、额度和实时可用状态依照平台当前说明及实际响应；本地配置不保证账户授权，也不绕过服务拒绝。
