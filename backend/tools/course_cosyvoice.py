"""Isolated CosyVoice 2 reference-voice inference for the course worker."""

import json
import sys
import wave
from pathlib import Path


MODEL_FILES = {
    "llm.pt": 2023316821,
    "flow.pt": 450575567,
    "hift.pt": 83390254,
    "campplus.onnx": 28303423,
    "speech_tokenizer_v2.onnx": 496082973,
    "CosyVoice-BlankEN/model.safetensors": 988097824,
    "CosyVoice-BlankEN/merges.txt": 1402109,
    "CosyVoice-BlankEN/vocab.json": 2776833,
}


def main(repo, weights, request_path):
    repo = Path(repo).resolve()
    weights = Path(weights).resolve()
    for name, size in MODEL_FILES.items():
        path = weights / name
        if not path.is_file() or path.stat().st_size != size:
            raise ValueError(f"CosyVoice 2 model file missing or incomplete: {name}")
    data = json.loads(Path(request_path).read_text(encoding="utf-8"))
    if data["voice_id"] or not data["reference_audio"] or not data["reference_text"].strip():
        raise ValueError("This driver expects a reference WAV and its transcript")
    if not data["text"].strip():
        raise ValueError("The narration must not be empty")
    with wave.open(data["reference_audio"], "rb") as sample:
        if not 3 <= sample.getnframes() / sample.getframerate() <= 30:
            raise ValueError("CosyVoice expects 3 to 30 seconds of reference audio")

    sys.path[:0] = [str(repo), str(repo / "third_party" / "Matcha-TTS")]
    import soundfile
    import torch
    from cosyvoice.cli.cosyvoice import AutoModel

    model = AutoModel(model_dir=str(weights), fp16=torch.cuda.is_available())
    chunks = [item["tts_speech"].cpu() for item in model.inference_zero_shot(
        data["text"], data["reference_text"], data["reference_audio"], stream=False,
    )]
    if not chunks:
        raise ValueError("CosyVoice returned no audio")
    audio = torch.cat(chunks, dim=-1).squeeze(0).float()
    if not torch.isfinite(audio).all() or audio.abs().max() == 0:
        raise ValueError("CosyVoice returned invalid or silent audio")
    soundfile.write(data["output"], audio.numpy(), model.sample_rate, subtype="PCM_16")


if __name__ == "__main__":
    main(*sys.argv[1:])
