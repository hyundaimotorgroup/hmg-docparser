"""Run the primary default PDF pipeline and compare it with its own saved baseline.

Use `--record-baseline` once before a material parser change, then run this script
again after the change. It deliberately makes live Dolphin, Paddle OCR, and LLM/VLM
calls (including router and global-context stages in default). Use --config for
local_quickstart; each DAG and input needs its own baseline.
"""

from __future__ import annotations

import argparse
import hashlib
from datetime import datetime, timezone
from difflib import SequenceMatcher
import json
from pathlib import Path
import re
import shutil
import sys
from uuid import uuid4

from dotenv import load_dotenv
import yaml


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
DEFAULT_CONFIG = ROOT / "configs" / "default.yaml"
DEFAULT_INPUT = ROOT / "inputs" / "smoke" / "dp_evalset_general_3p.pdf"
DEFAULT_OUTPUT_ROOT = ROOT / "outputs" / "regression" / "default_external"
TOKEN_PATTERN = re.compile(r"\w+", flags=re.UNICODE)
PAGE_PATTERN = re.compile(r"(?im)^@page:\s*")
HEADING_PATTERN = re.compile(r"(?m)^#{1,6}\s+")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-baseline", action="store_true", help="replace the saved baseline with this run")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument("--min-token-jaccard", type=float, default=0.80)
    parser.add_argument("--min-sequence-ratio", type=float, default=0.60)
    return parser.parse_args()


def _normalise(text: str) -> str:
    return " ".join(text.lower().split())


def _metrics(text: str) -> dict[str, int]:
    return {
        "characters": len(text),
        "lines": text.count("\n") + 1,
        "tokens": len(TOKEN_PATTERN.findall(_normalise(text))),
        "page_markers": len(PAGE_PATTERN.findall(text)),
        "headings": len(HEADING_PATTERN.findall(text)),
        "error_markers": text.count("[Error]"),
    }


def _token_jaccard(left: str, right: str) -> float:
    left_tokens = set(TOKEN_PATTERN.findall(_normalise(left)))
    right_tokens = set(TOKEN_PATTERN.findall(_normalise(right)))
    if not left_tokens and not right_tokens:
        return 1.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)


def _sequence_ratio(left: str, right: str) -> float:
    return SequenceMatcher(None, _normalise(left), _normalise(right), autojunk=False).ratio()


def _final_markdown_path(run_dir: Path, input_path: Path) -> Path:
    path = run_dir / f"{input_path.stem}.md"
    if not path.is_file():
        raise FileNotFoundError(f"pipeline did not produce final Markdown: {path}")
    return path


def _run_pipeline(*, config_path: Path, input_path: Path, run_dir: Path) -> Path:
    from core.engine.runtime import run_document_pipeline_from_config_path

    result = run_document_pipeline_from_config_path(
        str(config_path),
        input_path=str(input_path),
        output_path=str(run_dir),
        job_id=f"default-regression-{uuid4().hex}",
    )
    from core.services.markdown_validation import require_complete_document
    from core.domain.document.models import DocumentDTO
    for run in result.results_by_file.values():
        document = run.values_by_node.get(run.execution_order[-1])
        if isinstance(document, DocumentDTO):
            require_complete_document(document)
    if result.skipped_files:
        raise RuntimeError(f"pipeline skipped input files: {result.skipped_files}")
    return _final_markdown_path(run_dir, input_path)


def _baseline_identity(config_path: Path, input_path: Path) -> dict[str, str]:
    # Hash the unresolved graph, never resolved credentials or endpoints.
    template = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    graph = json.dumps(template["pipeline"], sort_keys=True, ensure_ascii=False).encode()
    return {
        "pipeline_sha256": hashlib.sha256(graph).hexdigest(),
        "input_sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
    }


def _write_metadata(path: Path, *, source: Path, metrics: dict[str, int], identity: dict[str, str]) -> None:
    path.write_text(
        json.dumps(
            {
                "source_markdown": str(source),
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "metrics": metrics,
                "identity": identity,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    load_dotenv(ROOT / ".env", override=False)

    config_path = args.config.resolve()
    input_path = args.input.resolve()
    output_root = args.output_root.resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"config not found: {config_path}")
    if not input_path.is_file():
        raise FileNotFoundError(f"input PDF not found: {input_path}")
    if not 0.0 <= args.min_token_jaccard <= 1.0 or not 0.0 <= args.min_sequence_ratio <= 1.0:
        raise ValueError("similarity thresholds must be between 0 and 1")

    baseline_path = output_root / "baseline.md"
    baseline_metadata = output_root / "baseline.metrics.json"
    if not args.record_baseline and not baseline_path.is_file():
        raise FileNotFoundError(
            f"baseline not found: {baseline_path}. Run once with --record-baseline before comparing."
        )
    identity = _baseline_identity(config_path, input_path)
    if not args.record_baseline:
        if not baseline_metadata.is_file():
            raise ValueError("baseline identity missing; record a baseline for this DAG and input")
        saved = json.loads(baseline_metadata.read_text(encoding="utf-8"))
        if saved.get("identity") != identity:
            raise ValueError("baseline DAG/input mismatch; use a separate output root and record its baseline")

    run_dir = output_root / "runs" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=False)
    print(f"Running {config_path.stem} regression: output={run_dir}")
    current_path = _run_pipeline(config_path=config_path, input_path=input_path, run_dir=run_dir)
    current = current_path.read_text(encoding="utf-8")
    current_metrics = _metrics(current)
    _write_metadata(run_dir / "metrics.json", source=current_path, metrics=current_metrics, identity=identity)

    if not current.strip() or current_metrics["error_markers"]:
        print("Pipeline produced empty Markdown or error markers; inspect this run.", file=sys.stderr)
        return 1
    if args.record_baseline:
        output_root.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(current_path, baseline_path)
        _write_metadata(baseline_metadata, source=baseline_path, metrics=current_metrics, identity=identity)
        print(f"Baseline recorded: {baseline_path}")
        return 0

    baseline = baseline_path.read_text(encoding="utf-8")
    baseline_metrics = _metrics(baseline)
    jaccard = _token_jaccard(baseline, current)
    sequence_ratio = _sequence_ratio(baseline, current)
    page_markers_match = baseline_metrics["page_markers"] == current_metrics["page_markers"]
    print(
        "Regression metrics: "
        f"token_jaccard={jaccard:.3f}, sequence_ratio={sequence_ratio:.3f}, "
        f"page_markers={baseline_metrics['page_markers']}->{current_metrics['page_markers']}, "
        f"baseline={baseline_path}, current={current_path}"
    )
    if not page_markers_match or jaccard < args.min_token_jaccard or sequence_ratio < args.min_sequence_ratio:
        print("Regression comparison failed; inspect the two Markdown files above.", file=sys.stderr)
        return 1
    print("Regression comparison passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
