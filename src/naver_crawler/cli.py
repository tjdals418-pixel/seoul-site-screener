from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Windows cp949 fallback — em-dash, 한글 stdin/stdout 깨짐 방지
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from naver_crawler.config import load_config
from naver_crawler.logging_setup import get_logger, setup_logging
from naver_crawler.pipeline.runner import Pipeline
from naver_crawler.pipeline.stages import ALL_STAGES


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="naver-crawler", description="Naver real-estate pipeline")
    p.add_argument(
        "--config",
        default="config/default.yaml",
        help="Path to YAML config (default: config/default.yaml)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    run_p = sub.add_parser("run", help="Run pipeline stages")
    run_p.add_argument("--from", dest="from_stage", help="Start at this stage")
    run_p.add_argument("--to", dest="to_stage", help="Stop after this stage")
    run_p.add_argument("--resume", action="store_true", help="Skip past last successful stage")

    sub.add_parser("list-stages", help="Show available stages and exit")

    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "list-stages":
        for s in ALL_STAGES:
            print(f"  {s.name:<10}  {s.title}")
        return 0

    cfg = load_config(args.config, project_root=Path(args.config).resolve().parent.parent)
    setup_logging(cfg.section("logging")["level"])
    log = get_logger("cli")

    valid = {s.name for s in ALL_STAGES}
    for k, v in (("--from", args.from_stage), ("--to", args.to_stage)):
        if v and v not in valid:
            log.error("unknown stage for %s: %r (run `list-stages`)", k, v)
            return 2

    Pipeline(ALL_STAGES, cfg).run(
        from_stage=args.from_stage,
        to_stage=args.to_stage,
        resume=args.resume,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
