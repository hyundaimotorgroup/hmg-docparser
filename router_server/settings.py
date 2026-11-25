from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8001


def checkpoint_paths() -> dict[str, Path]:
    """Return local checkpoint paths without importing optional ML dependencies."""
    model_dir = REPO_ROOT / "models" / "router"
    return {
        "binary": Path(os.getenv("ROUTER_BINARY_CHECKPOINT", model_dir / "binary_router.pth")),
        "fig": Path(os.getenv("ROUTER_FIG_CHECKPOINT", model_dir / "second_stage_fig.pth")),
        "tab": Path(os.getenv("ROUTER_TAB_CHECKPOINT", model_dir / "second_stage_tab.pth")),
    }


def missing_checkpoints() -> list[Path]:
    return [path for path in checkpoint_paths().values() if not path.is_file()]
