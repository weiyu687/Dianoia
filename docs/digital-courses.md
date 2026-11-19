# 数字课程部署与验收

教师可导入最多 40 页、50 MB 的 PPT/PPTX。编辑器提供「一键生成全部讲稿」「补齐空白页」和「AI 生成本页」。整课重生成替换现有可读页面前会确认。PPTX 讲者备注进入模型上下文。纯图像页可根据预览手动撰写。教师可上传正面形象 PNG/JPG，在声音档案内保存 3 至 30 秒的 WAV/MP3 或浏览器录音并填写原文。选择档案时，用该档案标记的参考样本做语音合成。预置形象与普通话音色放在单独的只读目录。

## 本地服务

- 按项目 README 启动 FastAPI。课件导入需要 LibreOffice Impress 和 Poppler 的 `pdftoppm`，音频导入和视频合成需要带 libx264 的 FFmpeg。可在 `backend/.env` 使用 `DIANOIA_SOFFICE`、`DIANOIA_PDFTOPPM` 和 `DIANOIA_FFMPEG` 指定绝对路径。
- 从 `backend` 目录使用项目 Python 环境运行 `python -m app.course_worker`。首版每个部署运行一个 worker。让 worker 和 Web API 使用同一 `DIANOIA_DATABASE_URL`、`DIANOIA_DATA_DIR`、文件访问权限和 LLM 配置。部署到 Linux GPU 主机时，API 与 worker 可以同机运行。进程管理器应在退出时重启 worker。
- 正常上传后可直接编写口播稿。AI 讲稿会进入队列。视频生产包括逐页合成语音、生成数字人、合成课件画面和合并 MP4。处理中的项目可离开页面后返回。运行任务失联超过两分钟后标记失败，可重新提交。整稿视频按任务新建，已成功的上一版在重制完成前可以继续下载。

## 模型环境

Dianoia 使用 SadTalker 的 512 人脸模型，按完整照片模式保留讲师的原图构图。处理长讲稿时，worker 按不超过 12 秒的音频片段渲染讲师并合并，再和课件及原始讲稿音轨一起封装为 720p MP4。

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

原版 CLI 在独立环境内启动。Dianoia 的启动脚本处理上游旧版库接口，并通过参数列表传给配置的 FFmpeg。推理前会检查四个官方权重的文件大小。先在编辑器选用预置形象和预置音色，制作两页短课件并检查旁置画面、口型及声音，再验收正式课程。当前成片采用静态课件画面，PPT 动画、内嵌媒体和字幕属于后续版式能力。[SadTalker 安装说明](https://github.com/OpenTalker/SadTalker/blob/main/docs/install.md) · [官方权重](https://github.com/OpenTalker/SadTalker/releases/expanded_assets/v0.0.2-rc)

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

如果部署选择 CosyVoice2-0.5B，可使用仓库中的参考驱动。按 CosyVoice 官方说明安装独立环境与模型，把下面四个路径换成部署主机上的实际路径。驱动处理教师上传样本，内置预设继续使用 Kokoro 环境。[CosyVoice2-0.5B 模型卡](https://huggingface.co/FunAudioLLM/CosyVoice2-0.5B)

```dotenv
DIANOIA_COURSE_TTS_COMMAND='["/opt/cosyvoice-env/bin/python","/opt/dianoia/backend/tools/course_cosyvoice.py","/opt/CosyVoice","/opt/models/CosyVoice2-0.5B"]'
```
