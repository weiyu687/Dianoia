"""Run the upstream SadTalker CLI in the dedicated rendering environment."""

import runpy
import subprocess
import sys
from pathlib import Path


def main():
    ffmpeg, script, *args = sys.argv[1:]
    script = Path(script).resolve()
    sys.path.insert(0, str(script.parent))

    import numpy as np
    from PIL import Image
    from torchvision.transforms import functional

    # The pinned upstream uses aliases removed by current NumPy, Pillow and torchvision.
    np.float = float
    if not hasattr(Image, "ANTIALIAS"):
        Image.ANTIALIAS = Image.Resampling.LANCZOS
    sys.modules.setdefault("torchvision.transforms.functional_tensor", functional)

    from src.face3d.util import preprocess

    original_pos = preprocess.POS

    def position(*args):
        translation, scale = original_pos(*args)
        return translation.reshape(2), scale

    preprocess.POS = position

    from src.utils import videoio

    upstream_mux = videoio.save_video_with_watermark

    def mux_video(video, audio, save_path, watermark=False):
        if watermark:
            return upstream_mux(video, audio, save_path, watermark=True)
        subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", video, "-i", audio,
                        "-c:v", "copy", save_path], check=True, stdin=subprocess.DEVNULL)

    videoio.save_video_with_watermark = mux_video
    sys.argv = [str(script), *args]
    runpy.run_path(str(script), run_name="__main__")


if __name__ == "__main__":
    main()
