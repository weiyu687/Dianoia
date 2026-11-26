# 数字课程部署与验收

教师可导入最多 40 页、50 MB 的 PPT/PPTX。编辑器提供「一键生成全部讲稿」「补齐空白页」和「AI 生成本页」。整课重生成替换现有可读页面前会确认。PPTX 讲者备注进入模型上下文。纯图像页可根据预览手动撰写。教师可上传正面形象 PNG/JPG，在声音档案内保存 3 至 30 秒的 WAV/MP3 或浏览器录音并填写原文。选择档案时，用该档案标记的参考样本做语音合成。预置形象与普通话音色放在单独的只读目录。

## 本地服务

- 按项目 README 启动 FastAPI。课件导入需要 LibreOffice Impress 和 Poppler 的 `pdftoppm`，音频导入和视频合成需要带 libx264 的 FFmpeg。可在 `backend/.env` 使用 `DIANOIA_SOFFICE`、`DIANOIA_PDFTOPPM` 和 `DIANOIA_FFMPEG` 指定绝对路径。
- 从 `backend` 目录使用项目 Python 环境运行 `python -m app.course_worker`。首版每个部署运行一个 worker。让 worker 和 Web API 使用同一 `DIANOIA_DATABASE_URL`、`DIANOIA_DATA_DIR`、文件访问权限和 LLM 配置。部署到 Linux GPU 主机时，API 与 worker 可以同机运行。进程管理器应在退出时重启 worker。
- 正常上传后可直接编写口播稿。AI 讲稿会进入队列。视频生产包括逐页合成语音、生成数字人、合成课件画面和合并 MP4。处理中的项目可离开页面后返回。运行任务失联超过两分钟后标记失败，可重新提交。整稿视频按任务新建，已成功的上一版在重制完成前可以继续下载。

## 分镜与试看

在编辑器的「画面预览」中选择背景主题和整课分镜。自动分镜让首尾页在演播室中出镜，正文页以课件全屏展示。可单独将某页改为演播室、全屏或画中画。画中画覆盖课件右下角，排版时可在画布确认遮挡。课件全屏只需声音，包含讲师的页面还需选定形象。

「试看本页」用该页开头的口播生成最多 12 秒的独立短片。短片使用正式生产的主题、构图、音色和讲师引擎，适用于检查文字可读性、音量和口型，整课成片保留在下方。改动并保存后可重新提交试看。成片为 1920×1080、25 fps 的 H.264/AAC MP4，保留原课件比例。新导入课件按更高分辨率渲染，旧项目可重新导入源文件以获得清晰原图。

服务器需要可绘制中文的系统字体。Windows 优先使用微软雅黑，Linux 可安装 Noto Sans CJK，也可用 `DIANOIA_COURSE_FONT` 指定字体文件。升级时 SQLite 由 API 和数字课程 worker 启动时迁移，PostgreSQL 在启动前执行 `python -m app.migrate`，迁移版本为 `20261126_05`。

## 模型环境

Dianoia 使用 SadTalker 的 512 人脸模型，按完整照片模式保留讲师的原图构图。处理长讲稿时，worker 按不超过 12 秒的音频片段渲染出镜页面，再和课程背景、课件及讲稿音轨合成。画面升级沿用现有权重，人物动作范围由 SadTalker 决定。

| 变量 | 取值 |
| --- | --- |
| `DIANOIA_SADTALKER_ROOT` | 含 `inference.py` 的 SadTalker 源码目录，默认 `DIANOIA_DATA_DIR/tools/SadTalker` |
| `DIANOIA_SADTALKER_PYTHON` | 独立推理环境的 Python 绝对路径，默认使用 SadTalker 目录中的 `.venv` |
| `DIANOIA_SADTALKER_CPU` | 设为 `true` 可显式选择 CPU，留空时使用 SadTalker 默认设备选择 |

Windows 示例在 Dianoia 仓库根目录运行，使用项目 Python 3.12 环境创建独立的 SadTalker 环境。GPU 需运行支持 CUDA 12.4 的 NVIDIA 驱动。

```powershell
$root = 'backend/data/tools/SadTalker'
git clone https://github.com/OpenTalker/SadTalker.git $root
git -C $root checkout --detach cd4c0465ae0b54a6f85af57f5c65fec9fe23e7f8
.\.venv\Scripts\python.exe -m venv "$root/.venv"
$python = "$root/.venv/Scripts/python.exe"
& $python -m pip install torch==2.6.0 torchvision==0.21.0 --index-url https://download.pytorch.org/whl/cu124
& $python -m pip install 'setuptools<81' wheel
& $python -m pip install pip==25.3
& $python -m pip install --no-build-isolation -r backend/requirements-sadtalker.txt

$checkpoints = "$root/checkpoints"
$face = "$root/gfpgan/weights"
New-Item -ItemType Directory -Force $checkpoints, $face | Out-Null
$sad = 'https://github.com/OpenTalker/SadTalker/releases/download/v0.0.2-rc'
$facexlib = 'https://github.com/xinntao/facexlib/releases/download/v0.1.0'
Invoke-WebRequest "$sad/SadTalker_V0.0.2_512.safetensors" -OutFile "$checkpoints/SadTalker_V0.0.2_512.safetensors"
Invoke-WebRequest "$sad/mapping_00109-model.pth.tar" -OutFile "$checkpoints/mapping_00109-model.pth.tar"
Invoke-WebRequest "$facexlib/alignment_WFLW_4HG.pth" -OutFile "$face/alignment_WFLW_4HG.pth"
Invoke-WebRequest "$facexlib/detection_Resnet50_Final.pth" -OutFile "$face/detection_Resnet50_Final.pth"
```

原版 CLI 在独立环境内启动。Dianoia 的启动脚本处理上游旧版库接口，并通过参数列表传给配置的 FFmpeg。推理前会检查四个官方权重的文件大小。先用「试看本页」核对画面、口型和声音，再提交正式课程。课件在视频中按页静态展示，PPT 动画、内嵌媒体和字幕待后续接入。[SadTalker 安装说明](https://github.com/OpenTalker/SadTalker/blob/main/docs/install.md) · [官方权重](https://github.com/OpenTalker/SadTalker/releases/expanded_assets/v0.0.2-rc)

2026-11-19 本机验收通过。RTX 4070 SUPER 12GB、Windows、Python 3.12 与上述 CUDA 环境，经常规 API 用预置形象和 Kokoro 语音生成两页课程。成片长 23.701 秒，处理耗时 244 秒，测试期间 GPU 总显存峰值 6966 MiB。该数字包括测试前约 1170 MiB 的桌面占用。结果用于确认此配置可完成短课件，正式长课程应继续检验段间表情过渡及不同照片。

### 预置普通话音色

在独立 Python 环境安装 `kokoro==0.9.4`、`misaki[zh]>=0.9.4,<0.10` 和 `soundfile`，按上游说明配置系统 espeak-ng。将该环境的 Python 路径填入 `DIANOIA_COURSE_KOKORO_PYTHON`，并在部署时下载 `hexgrad/Kokoro-82M-v1.1-zh` 模型与所选音色权重。预听文件是模型卡示例的前 5 秒，转为 16 kHz 单声道 WAV。图像由内置 ImageGen 生成，提示为面向高校数字讲课制作虚构中国讲师，分别为蓝灰背景蓝色西装女讲师、暖灰背景深色西装男讲师，正面半身、固定镜头、闭口、无文字。 [Kokoro 示例音频及许可](https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/tree/f3ddd5d/samples)

如果模型缓存使用独立目录，设置 `DIANOIA_COURSE_KOKORO_HOME` 为该 Hugging Face 缓存根目录。在编辑器里选择预置音色，使用「试听本页讲稿」验证当前文本的实际语音输出。试听任务只调用语音引擎。

### 教师音频样本和自定义预置音色

设置 `DIANOIA_COURSE_TTS_COMMAND` 为 JSON 字符串数组，内容是部署所选语音合成程序及固定参数。worker 在参数末尾追加 UTF-8 JSON 请求文件路径。请求字段如下。

```json
{
  "text": "要朗读的讲稿",
  "voice_id": null,
  "reference_audio": "/data/project/jobs/snapshot/voice.wav",
  "reference_text": "样本实际朗读的文字",
  "output": "/data/project/jobs/snapshot/page-1/speech.wav"
}
```

程序成功时退出码为 0，将 PCM 16 位 WAV 写入 `output`。`voice_id` 为空时使用样本与原文做零样本合成。`voice_id` 有值时按部署中的音色 ID 合成，样本路径为空。可通过 `DIANOIA_COURSE_PRESET_VOICES` 指定其他预置音色 JSON 文件，格式为 `[{"id":"mandarin03","name":"普通话讲授","preview":"samples/mandarin03.wav"}]`。在与实际选定的语音引擎完成验收前，教师样本可上传试听并管理。

### CosyVoice 2 个人音色

使用 CosyVoice2-0.5B 做零样本合成。每次使用一条参考录音及其原文，不需要训练。声音档案中的多条样本用于挑选更合适的参考，不会自动合并训练。内置预设继续使用 Kokoro 环境。[CosyVoice2-0.5B 模型卡](https://huggingface.co/FunAudioLLM/CosyVoice2-0.5B)

在仓库根目录为 GPU 推理安装独立环境。Windows 验证配置为 Python 3.12、PyTorch / torchaudio 2.6.0 + CUDA 12.4；其余固定依赖见 `backend/requirements-cosyvoice.txt`。不要把这些推理依赖安装进 Web API 环境。

```powershell
$cosy = 'backend/data/tools/CosyVoice'
git clone https://github.com/FunAudioLLM/CosyVoice.git $cosy
git -C $cosy checkout --detach 074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc
git -C $cosy submodule update --init --recursive
.\.venv\Scripts\python.exe -m venv "$cosy/.venv"
$cosyPython = "$cosy/.venv/Scripts/python.exe"
& $cosyPython -m pip install torch==2.6.0 torchaudio==2.6.0 --index-url https://download.pytorch.org/whl/cu124
& $cosyPython -m pip install setuptools==78.1.0 wheel==0.48.0
& $cosyPython -m pip install --no-build-isolation -r backend/requirements-cosyvoice.txt -c backend/constraints-cosyvoice.txt
& $cosyPython -c "from huggingface_hub import snapshot_download; snapshot_download('FunAudioLLM/CosyVoice2-0.5B', revision='eec1ae6c79877dbd9379285cf8789c9e0879293d', local_dir='backend/data/tools/CosyVoice/models/CosyVoice2-0.5B', allow_patterns=['*.pt', 'cosyvoice2.yaml', 'campplus.onnx', 'speech_tokenizer_v2.onnx', 'CosyVoice-BlankEN/*'])"
```

上述推理文件总计约 4.07 GB（3.79 GiB），不含 Python/CUDA 运行环境。文本规范化采用自带 FST 资源的 WeText 0.2.1，无需在首次讲稿合成时从 ModelScope 下载词法模型。驱动启动前检查必要权重的大小，避免不完整下载直接进入推理。GPU 可用时使用 FP16；任务结束后独立推理进程退出，释放显存，再进入 SadTalker 渲染。

在 `backend/.env` 配置下述四个绝对路径，并重启 API 和 course worker。Linux 示例可换成本机路径；Windows JSON 数组内使用正斜杠。

```dotenv
DIANOIA_COURSE_TTS_COMMAND='["/opt/cosyvoice-env/bin/python","/opt/dianoia/backend/tools/course_cosyvoice.py","/opt/CosyVoice","/opt/models/CosyVoice2-0.5B"]'
```

使用步骤：进入「数字课程 → 音色与样本库 → 我的」，新建声音档案，录制或上传 3–30 秒清晰的单人录音，填写准确原文，指定「合成参考」。建议自然朗读 6–15 秒，保留完整句子。在课程编辑器选择该声音档案，保存后点击「试听本页讲稿」，确认新讲稿的读音与音色，再提交视频。试音和正式生产使用相同参考音频与原文；排队时复制参考录音作为任务快照。

2026-11-19 已在本机配置并重启 API 和 worker。参考录音使用平台合成的测试音频，独立 CLI 生成不同内容的 5.44 秒 WAV，耗时 28.2 秒；声音档案试音 API 输出 5.6 秒 WAV，耗时 20.7 秒，删除原样本后任务快照仍可使用。相同个人音色通过 SadTalker 导出 5.621 秒的 1280×720 H.264/AAC MP4，视频任务耗时 125.5 秒。上述耗时包含每次独立进程的模型加载，仅用于描述短讲稿测试，不代表长课程速度或真实教师录音的音色相似度。
