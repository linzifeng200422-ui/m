---
name: m
description: m（统一语音工具）；以工具名提到 m、M 或 $m，或需要人声转写、语音识别、配音、旁白、朗读、音色克隆和声音设计时使用。ASR 使用已有本地 Whisper，不调用 MiMo、不上传素材；TTS、VoiceClone、VoiceDesign 使用 MiMo。也识别 mimotts/MiMoTTS/小米配音/音频克隆生成。明确指定其他服务时遵从其选择；不负责音乐、音效、降噪或视频时间线。
---

# m · 统一语音工具

技能名为 `m`，统一本地 Whisper 转写与 MiMo 三种语音合成能力。用户以工具名称提到 m / M / $m 即识别为本工具；普通代码变量、数学符号或长度单位 m 不误触发。旧称 mimotts / MiMoTTS / 音频克隆生成继续识别，历史配音命令通过仓库内兼容入口 `scripts/voiceclone.py` 继续有效。

语音识别复用系统 PATH 中已有的本地 Whisper CLI；不修改剪辑时间线，亦不恢复云端 ASR。

## 按任务选功能

| 用户要做的事 | 子命令 / 模型 | 必要输入 → 输出 |
| --- | --- | --- |
| 录音转文字、提取视频说话内容、生成字幕 | `asr` / 本地 Whisper | 本地音视频 → TXT/SRT/VTT/TSV/JSON（含逐词时间戳） |
| 给文案配音、旁白、朗读；无克隆或设计要求 | `tts` / `mimo-v2.5-tts` | 完整文案 + 预置音色 → WAV |
| 用所给参考声音朗读新文案 | `voiceclone` / `mimo-v2.5-tts-voiceclone` | 完整文案 + 参考 WAV/MP3 → WAV |
| 根据年龄、口音、质感等描述创造声线 | `voicedesign` / `mimo-v2.5-tts-voicedesign` | 完整文案 + 声音描述 → WAV |

按意图直接选模式，不让用户选择内部模型。只说配音且没有既定声线时用预置 TTS；仅当明确要求克隆而缺少参考文件，或任务对象不清楚时询问实际缺项。单纯讨论声音、问功能或方法只读取说明，不提交请求。完整视频流程可以调用本 Skill 的语音步骤，后续画面、字幕对齐或剪辑仍由其原工作流负责。

## MiMo 合成：固定接口与授权约定

- 三种 MiMo 合成模式固定使用 `https://token-plan-cn.xiaomimimo.com/v1`。这是项目唯一 `base_url`；不改成普通按量 API 域名，不自动切换集群、账户或提供方。各模型的参数结构按官方文档分别构建。
- 每次任务授权覆盖具体音频和用途：用户交给 MiMo 处理的本次指定音频（包括本次任务选定的参考片段），即代表已有上传 MiMo 完成该任务的授权，已获得授权则不重复确认。此约定不意味着主动收集其他私人音频，亦不授权转交第三方服务；仅询问功能、方法或讨论声音时不提交请求、不上传音频；不添加多余的 `confirm-upload` 开关。
- 凭据优先读取环境变量 `MIMO_API_KEY`，为空时读取本机安全文件 `~/.config/mimotts/api-key`。文件须为当前用户所有、不可由其他用户访问，推荐目录 700 / 文件 600；拒绝凭据文件符号链接。**代码不会自动读取 `.env`**。不要打印、复制或转交密钥；环境变量为空不等于未配置。

## 执行与用法

**执行某个模式时读取 [功能使用说明](references/usage.md) 的对应章节**；包含自然语言示例、完整命令、预置音色列表、语气控制、格式转换和故障定位。统一入口为 `scripts/m_audio.py`；旧入口 `scripts/voiceclone.py` 继续兼容：

```bash
python3 scripts/m_audio.py --help
python3 scripts/m_audio.py asr --audio /absolute/input.wav --output-dir /absolute/new-transcript --language zh --dry-run
python3 scripts/m_audio.py voices
python3 scripts/m_audio.py tts --text-file /absolute/script.txt --voice 苏打 --output /absolute/voice.wav --dry-run
python3 scripts/m_audio.py voiceclone --text-file /absolute/script.txt --reference-audio /absolute/reference.wav --output /absolute/clone.wav --dry-run
python3 scripts/m_audio.py voicedesign --text-file /absolute/script.txt --description '普通话，中年男性，略沙哑，沉稳' --output /absolute/design.wav --dry-run
```

从其他目录或作为 Skill 调用时，可使用脚本的完整路径。本地 ASR 复用已有 Whisper CLI 运行环境；MiMo 合成复用已有 Python + `openai` 环境。离线检查与音色列表不需密钥、不请求网络、不生成成品；确认输入有效后，在实际执行请求已覆盖的范围内去掉 `--dry-run` 调用一次，无需再问上传。MiMo 参考音频的 MP3 检查需要本地 `ffprobe`；WAV 检查不需要。缺依赖时优先已有环境，确实缺失再用项目虚拟环境，不做全局安装。

## 本地 ASR

读取 [本地 Whisper 用法](references/usage.md#本地-whisper转写)。默认复用 `~/.cache/whisper/base.pt`，显式传本地模型路径，CPU、FP32、逐词时间戳。只检查和使用现有模型，不自动安装、下载或回退云服务，不读 MiMo 凭据。缺依赖或模型时报告实际缺项。识别不是翻译；时间戳是模型估计，中文词块不等同于严格逐字对齐，不承诺说话人分离。空转写明确报告。音视频由本地 FFmpeg 解码，不受 MiMo 的 10 MB 限制。

## MiMo 合成必须保持的行为

- **完整文案原样提交，一次合成。** 三种合成模式的目标全文在 `assistant.content`；表达指令在 `user.content`。不默认拆句或拼接。风格优先用独立指令；正文里的情绪标签仅在用户要求时加入。
- **音色设计保留原稿。** 声音描述写入 `user.content`，`audio.optimize_text_preview=false`；不能照搬官网示例中的 `true` 自动改写待朗读内容。
- **克隆无需注册。** 参考音频的 data URI 写入 `audio.voice`，不要求对应转写、训练或 voice ID；预置 TTS 才使用具名 voice ID。
- 音频输入仅 WAV/MP3，Base64 后不超过 10 MB；脚本 WAV 路径校验实际 PCM 内容。视频/M4A/其他 WAV 编码先用本地 FFmpeg 转换，不能只改扩展名。超限先合理压缩或选取片段，不静默批量拆分请求。
- 输出不覆盖已有文件；三种合成保存服务返回的完整 WAV，保留实际采样率和声道。需其他规格时另存本地转换版本。
- SDK 自动重试为 0，默认超时 300 秒，可用 `--timeout` 调整。超时/断连视为结果不确定，核对状态后决定下一步，不自行重复提交。错误只显示安全摘要，不回显请求全文、音频 Base64 或 SDK 错误正文。
- 保存前检查返回音频有效，拒绝明显未正常完成或截断的返回。配音交付可播放文件；音色相似度、发音和听感须实际试听，不能用离线测试或接口成功代替。

## 验证边界与来源

本地 ASR 路由测试：`python3 scripts/test_m_audio.py`。MiMo 本地测试：`python3 scripts/test_mimo_audio.py`（使用合成测试音频、假密钥和内存 HTTP 响应，不上传任何音频、不调用真实 MiMo）。离线测试不证明真实 Token Plan 服务、额度或听感；不要把本地通过写成线上可用已验证。

参考官方资料：[TTS 三种模式使用指南](https://mimo.mi.com/docs/zh-CN/quick-start/usage-guide/audio/speech-synthesis-v2.5)、[Token Plan 接入](https://mimo.mi.com/docs/zh-CN/tokenplan/Token%20Plan/quick-access)。套餐可用性和适用范围以服务端及当前官方说明为准；本地配置不保证账户授权，拒绝时定位原因而非静默换域名。
