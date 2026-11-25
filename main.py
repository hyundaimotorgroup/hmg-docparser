import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile and run a PDF parsing pipeline from a native YAML config."
    )
    parser.add_argument(
        "config_path",
        nargs="?",
        default="configs/default.yaml",
        help="native YAML config path (default: %(default)s)",
    )
    return parser.parse_args()


def run(config_path: str) -> None:
    from core.engine.runtime import run_document_pipeline_from_config_path
    from core.observability import CliProgressObserver

    run_document_pipeline_from_config_path(config_path, observers=[CliProgressObserver()])


if __name__ == "__main__":
    args = parse_args()
    run(args.config_path)
