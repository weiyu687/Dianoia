"""Fetch only the upstream checkpoints needed by the official single-person FP8 CLI."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from huggingface_hub import hf_hub_download


ASSETS = (
    ("MeiGen-AI/InfiniteTalk", "main", "InfiniteTalk", (
        "quant_models/infinitetalk_single_fp8.safetensors", "quant_models/infinitetalk_single_fp8.json",
        "quant_models/t5_fp8.safetensors", "quant_models/t5_map_fp8.json",
    )),
    ("Wan-AI/Wan2.1-I2V-14B-480P", "main", "Wan2.1-I2V-14B-480P", (
        "config.json", "Wan2.1_VAE.pth", "models_clip_open-clip-xlm-roberta-large-vit-huge-14.pth",
        "google/umt5-xxl/special_tokens_map.json", "google/umt5-xxl/spiece.model",
        "google/umt5-xxl/tokenizer.json", "google/umt5-xxl/tokenizer_config.json",
        "xlm-roberta-large/sentencepiece.bpe.model", "xlm-roberta-large/special_tokens_map.json",
        "xlm-roberta-large/tokenizer.json", "xlm-roberta-large/tokenizer_config.json",
    )),
    ("TencentGameMate/chinese-wav2vec2-base", "refs/pr/1", "chinese-wav2vec2-base", (
        "config.json", "preprocessor_config.json", "model.safetensors",
    )),
)


def main(root):
    def fetch(item):
        repo, revision, directory, filename = item
        print(f"Fetching {repo}/{filename}", flush=True)
        path = hf_hub_download(repo, filename=filename, revision=revision, local_dir=root / directory)
        print(f"Ready {Path(path).relative_to(root)}", flush=True)

    files = [(repo, revision, directory, name) for repo, revision, directory, names in ASSETS for name in names]
    with ThreadPoolExecutor(max_workers=6) as downloads:
        list(downloads.map(fetch, files))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("weights", type=Path)
    main(parser.parse_args().weights.resolve())
