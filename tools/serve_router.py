#!/usr/bin/env python3
"""Serve the optional router models on loopback only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Running a file under tools/ makes that directory the import root; expose the
# repository-local optional package without requiring it to be installed.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from router_server.settings import DEFAULT_HOST, DEFAULT_PORT, checkpoint_paths, missing_checkpoints


LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default=DEFAULT_HOST, help="loopback host only (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="local port (default: 8001)")
    parser.add_argument("--check", action="store_true", help="verify checkpoint paths and exit")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.host not in LOOPBACK_HOSTS:
        print("router server is local-only; --host must be a loopback address", file=sys.stderr)
        return 2
    if not 1 <= args.port <= 65535:
        print("--port must be between 1 and 65535", file=sys.stderr)
        return 2

    missing = missing_checkpoints()
    if missing:
        for path in missing:
            print(f"missing router checkpoint: {path}", file=sys.stderr)
        return 1
    if args.check:
        print(f"router checkpoints ready; set ROUTER_SERVER_URL=http://{args.host}:{args.port}")
        for name, path in checkpoint_paths().items():
            print(f"{name}: {path}")
        return 0

    try:
        import uvicorn
    except ImportError:
        print("install dependencies: pip install -r requirements.txt", file=sys.stderr)
        return 1
    uvicorn.run("router_server.main:app", host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
