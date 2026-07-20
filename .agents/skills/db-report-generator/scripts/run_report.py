"""CLI entrypoint: .env -> report_data.json + rendered reports."""
import json
import sys
from pathlib import Path

from scripts import analyzer, render
from scripts.lib.envparse import parse_env

USAGE = "usage: python -m scripts.run_report <path-to-.env> <output-dir>"


def run(env_path: Path, out_dir: Path) -> dict:
    cfg = parse_env(Path(env_path))
    report = analyzer.analyze([cfg])
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "report_data.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )
    render.render_all(report, out_dir)
    return report


def main(argv: list[str]) -> int:
    if len(argv) != 3:
        print(USAGE, file=sys.stderr)
        return 2
    env_path, out_dir = Path(argv[1]), Path(argv[2])
    if not env_path.exists():
        print(f"error: .env file not found: {env_path}", file=sys.stderr)
        return 2
    try:
        run(env_path, out_dir)
    except ValueError as exc:
        print(f"error: invalid .env: {exc}", file=sys.stderr)
        return 1
    print(f"OK: report written to {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
