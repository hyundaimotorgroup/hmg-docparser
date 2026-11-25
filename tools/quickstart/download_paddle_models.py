"""Download both quickstart OCR models and the Korean dictionary for transfer."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import urllib.request

# Set before huggingface_hub is imported, matching the Dolphin download path.
os.environ.setdefault("HF_HUB_DISABLE_XET", "1")

from huggingface_hub import snapshot_download
import truststore

MODELS = {
    "PP-OCRv5_mobile_det": "0d63e78e2b680928f6b1747d76a08db6e645efb7",
    "korean_PP-OCRv5_mobile_rec": "c02ecaf1f22bfd1c618cce154fd19185b47e663a",
}
DICTIONARY_URL = (
    "https://raw.githubusercontent.com/PaddlePaddle/PaddleOCR/v3.1.0/"
    "ppocr/utils/dict/ppocrv5_korean_dict.txt"
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=Path("models/paddle"))
    args = parser.parse_args()
    truststore.inject_into_ssl()
    output = args.output_dir.expanduser().resolve()
    for name, revision in MODELS.items():
        print(f"Downloading PaddlePaddle/{name} at {revision} into {output / name}", flush=True)
        snapshot_download(repo_id=f"PaddlePaddle/{name}", revision=revision, local_dir=output / name)
    dictionary_path = output / "korean_PP-OCRv5_mobile_rec" / "ppocrv5_korean_dict.txt"
    print(f"Downloading Korean dictionary into {dictionary_path}", flush=True)
    with urllib.request.urlopen(DICTIONARY_URL, timeout=120) as response:
        dictionary_bytes = response.read()
    dictionary = dictionary_bytes.decode("utf-8").splitlines()
    if len(dictionary) < 3000 or not any("가" <= character <= "힣" for character in dictionary):
        raise RuntimeError("Downloaded Korean dictionary is invalid")
    dictionary_path.write_bytes(dictionary_bytes)
    (output / "download-provenance.json").write_text(
        json.dumps({"models": MODELS, "dictionary_url": DICTIONARY_URL}, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Ready to transfer the entire directory: {output}", flush=True)


if __name__ == "__main__":
    main()
