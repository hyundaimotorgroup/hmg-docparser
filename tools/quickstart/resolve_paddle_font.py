"""Find a usable PaddleX font or cache a verified Noto Sans KR download."""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from dotenv import load_dotenv
from PIL import ImageFont

ROOT = Path(__file__).resolve().parents[2]
FONT_BASE_URL = (
    "https://raw.githubusercontent.com/google/fonts/"
    "83c62e30d87daa70216dab6b984d00d20d96d585/ofl/notosanskr/"
)
FONT_ASSETS = (
    ("NotoSansKR.ttf", "NotoSansKR%5Bwght%5D.ttf",
     "194018e6b2b293a7964f037b25c0249ce1418bc9ab3c971060a03aa57861e252"),
    ("OFL.txt", "OFL.txt",
     "1c05c68c34f9708415aada51f17e1b0092d2cea709bf4a94cd38114f9e73d7d9"),
)


def usable_font(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        ImageFont.truetype(str(path), 12)
    except (OSError, ValueError):
        return False
    return True


def installed_fonts():
    yield Path("/System/Library/Fonts/AppleSDGothicNeo.ttc")
    yield Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    yield Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf")
    # Fontconfig knows distro-specific and user-installed font locations.
    try:
        result = subprocess.run(
            ["fc-match", "--format=%{file}", "sans-serif"],
            capture_output=True, text=True, timeout=10, check=True,
        )
        if result.stdout.strip():
            yield Path(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        pass
    for directory in (
        Path("/usr/share/fonts"), Path("/usr/local/share/fonts"),
        Path("/Library/Fonts"), Path("/System/Library/Fonts"),
        Path.home() / ".fonts", Path.home() / ".local/share/fonts",
        Path.home() / "Library/Fonts",
    ):
        if directory.is_dir():
            for path in sorted(directory.rglob("*")):
                if path.suffix.lower() in {".ttf", ".ttc", ".otf"}:
                    yield path


def checksum_matches(path: Path, expected: str) -> bool:
    return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == expected


def download_font(cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    for name, remote_name, checksum in FONT_ASSETS:
        destination = cache_dir / name
        if checksum_matches(destination, checksum):
            continue
        print(f"Downloading PaddleX font asset: {name}", file=sys.stderr)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{name}-", dir=cache_dir)
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            subprocess.run(
                ["curl", "--fail", "--location", "--silent", "--show-error",
                 "--retry", "3", "--connect-timeout", "15", "--max-time", "120",
                 FONT_BASE_URL + remote_name, "--output", str(temporary)],
                check=True,
            )
            if not checksum_matches(temporary, checksum):
                raise ValueError(f"font asset checksum mismatch: {name}")
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
    font = cache_dir / FONT_ASSETS[0][0]
    if not usable_font(font):
        raise ValueError("downloaded font cannot be loaded by Pillow")
    return font.resolve()


def resolve_font(cache_dir: Path) -> Path:
    explicit = os.getenv("PADDLE_PDX_LOCAL_FONT_FILE_PATH")
    if explicit:
        path = Path(explicit).expanduser().resolve()
        if not usable_font(path):
            raise ValueError(f"PADDLE_PDX_LOCAL_FONT_FILE_PATH is not a usable font: {path}")
        return path
    for path in installed_fonts():
        if usable_font(path):
            return path.resolve()
    return download_font(cache_dir)


if __name__ == "__main__":
    load_dotenv(ROOT / ".env")
    try:
        print(resolve_font(Path(sys.argv[1])))
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(f"ERROR: could not prepare PaddleX font: {error}; "
                 "set PADDLE_PDX_LOCAL_FONT_FILE_PATH to a usable installed font")
