from __future__ import annotations

from pathlib import Path
import shutil
from typing import TYPE_CHECKING

from core.domain.artifacts import ArtifactRef
from core.interfaces.adapters import ArtifactStore

if TYPE_CHECKING:
    from PIL import Image


class LocalArtifactStore(ArtifactStore):
    def __init__(self, root_dir: str | Path) -> None:
        self._root_dir = Path(root_dir)
        self._root_dir.mkdir(parents=True, exist_ok=True)

    def save(self, artifact: object, *, name: str | None = None) -> ArtifactRef:
        if isinstance(artifact, bytes):
            return self._save_bytes(artifact, name=name)
        if isinstance(artifact, str):
            return self._save_text(artifact, name=name)
        if isinstance(artifact, Path):
            return self._copy_path(artifact, name=name)
        if _is_pil_image(artifact):
            return self._save_image(artifact, name=name)
        raise TypeError(f"unsupported artifact type: {type(artifact).__name__}")

    def _save_bytes(self, data: bytes, *, name: str | None) -> ArtifactRef:
        path = self._resolve_name(name, default_name="artifact.bin")
        path.write_bytes(data)
        return ArtifactRef(path=str(path), media_type=_media_type_for_path(path))

    def _save_text(self, text: str, *, name: str | None) -> ArtifactRef:
        path = self._resolve_name(name, default_name="artifact.txt")
        path.write_text(text, encoding="utf-8")
        return ArtifactRef(path=str(path), media_type=_media_type_for_path(path))

    def _copy_path(self, source: Path, *, name: str | None) -> ArtifactRef:
        if not source.exists():
            raise FileNotFoundError(f"artifact source not found: {source}")
        path = self._resolve_name(name, default_name=source.name)
        shutil.copy2(source, path)
        return ArtifactRef(path=str(path), media_type=_media_type_for_path(path))

    def _save_image(self, image: "Image.Image", *, name: str | None) -> ArtifactRef:
        path = self._resolve_name(name, default_name="artifact.png")
        image.save(path)
        return ArtifactRef(path=str(path), media_type=_media_type_for_path(path))

    def _resolve_name(self, name: str | None, *, default_name: str) -> Path:
        candidate = Path(name or default_name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise ValueError(f"artifact name must be relative to store root: {name}")
        path = self._root_dir / candidate
        path.parent.mkdir(parents=True, exist_ok=True)
        return path


def _is_pil_image(value: object) -> bool:
    return hasattr(value, "save") and value.__class__.__module__.startswith("PIL.")


def _media_type_for_path(path: Path) -> str | None:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return "application/json"
    if suffix in {".html", ".htm"}:
        return "text/html"
    if suffix in {".md", ".txt"}:
        return "text/markdown" if suffix == ".md" else "text/plain"
    if suffix == ".pdf":
        return "application/pdf"
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        image_type = "jpeg" if suffix in {".jpg", ".jpeg"} else suffix.lstrip(".")
        return f"image/{image_type}"
    return None
