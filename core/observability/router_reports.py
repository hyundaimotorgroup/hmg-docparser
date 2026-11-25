"""Concurrent page-worker router evidence, separate from legacy block reports."""
from __future__ import annotations

import json
from pathlib import Path
from threading import RLock

_LOCK = RLock()


def append_router_records(context, filename, records):
    runtime = context.metadata.get('runtime_config', {})
    output = runtime.get('outputs') if isinstance(runtime, dict) else None
    if not output or not records:
        return
    path = Path(output) / filename
    append_jsonl(path, records)


def append_jsonl(path, records):
    # One lock spans the complete write; parallel workers cannot interleave lines.
    content = ''.join(json.dumps(record, ensure_ascii=False) + '\n' for record in records)
    with _LOCK:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with Path(path).open('a', encoding='utf-8') as file:
            file.write(content)
