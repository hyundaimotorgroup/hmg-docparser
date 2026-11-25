from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ArtifactRef:
    path: str
    media_type: str | None = None
    description: str | None = None
