"""Optional preset narration driver, run in the Kokoro environment."""

import json
import sys
from pathlib import Path


def synthesize(request):
    import numpy as np
    import soundfile
    from kokoro import KPipeline

    repo = "hexgrad/Kokoro-82M-v1.1-zh"
    english = KPipeline(lang_code="a", repo_id=repo, model=False)

    def english_phonemes(text):
        result = next(english(text), None)
        return result.phonemes if result else ""

    pipeline = KPipeline(lang_code="z", repo_id=repo, en_callable=english_phonemes, device="cpu")
    chunks = [result.audio.numpy() for result in pipeline(request["text"], voice=request["voice_id"])
              if result.audio is not None]
    if not chunks:
        raise ValueError("Kokoro returned no audio")
    soundfile.write(request["output"], np.concatenate(chunks), 24000, subtype="PCM_16")


if __name__ == "__main__":
    synthesize(json.loads(Path(sys.argv[1]).read_text(encoding="utf-8")))
