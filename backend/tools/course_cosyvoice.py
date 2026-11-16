"""Optional reference-voice driver for an installed CosyVoice 2 environment."""

import json
import sys
from pathlib import Path


def main(repo, weights, request_path):
    repo = Path(repo).resolve()
    sys.path[:0] = [str(repo), str(repo / "third_party" / "Matcha-TTS")]
    import soundfile
    import torch
    from cosyvoice.cli.cosyvoice import AutoModel

    data = json.loads(Path(request_path).read_text(encoding="utf-8"))
    if data["voice_id"] or not data["reference_audio"] or not data["reference_text"]:
        raise ValueError("This driver expects a reference WAV and its transcript")

    model = AutoModel(model_dir=str(Path(weights).resolve()))
    chunks = [item["tts_speech"].cpu() for item in model.inference_zero_shot(
        data["text"], data["reference_text"], data["reference_audio"], stream=False,
    )]
    if not chunks:
        raise ValueError("CosyVoice returned no audio")
    audio = torch.cat(chunks, dim=-1).squeeze(0).numpy()
    soundfile.write(data["output"], audio, model.sample_rate, subtype="PCM_16")


if __name__ == "__main__":
    main(*sys.argv[1:])
