from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from typing import Optional, Sequence

import publish_all

SCHEDULE_FORMAT = "%Y-%m-%d %H:%M"


def schedule_value(value: str) -> datetime:
    try:
        return datetime.strptime(value, SCHEDULE_FORMAT)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"Invalid schedule '{value}'. Expected format: {SCHEDULE_FORMAT}"
        ) from exc


def build_parser() -> argparse.ArgumentParser:
    schedule_help = SCHEDULE_FORMAT.replace("%", "%%")
    parser = argparse.ArgumentParser(
        prog="hgsau",
        description="CLI for social-auto-upload.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    publish_parser = subparsers.add_parser(
        "publish",
        help="Publish to multiple platforms",
    )
    publish_parser.add_argument(
        "--config",
        default="publish_config.ini",
        help="Config file path (default: publish_config.ini)",
    )
    publish_parser.add_argument(
        "--platforms",
        default=None,
        help="Override enabled platforms, comma-separated",
    )
    publish_parser.add_argument(
        "--video",
        default=None,
        help="Override video file/directory path",
    )
    publish_parser.add_argument("--title", default=None, help="Override title")
    publish_parser.add_argument("--desc", default=None, help="Override description")
    publish_parser.add_argument(
        "--tags",
        default=None,
        help="Override tags, comma-separated",
    )
    publish_parser.add_argument(
        "--schedule",
        type=schedule_value,
        default=None,
        help=f"Override schedule time in {schedule_help}",
    )
    publish_parser.add_argument(
        "--start-from",
        type=int,
        default=None,
        help="Start from video index (1-based)",
    )
    publish_parser.add_argument(
        "--force",
        action="store_true",
        help="Force regenerate video config",
    )
    return parser


def build_overrides(args: argparse.Namespace) -> publish_all.PublishOverrides:
    return publish_all.PublishOverrides(
        platforms=args.platforms,
        video=args.video,
        title=args.title,
        desc=args.desc,
        tags=args.tags,
        schedule=args.schedule,
        start_from=args.start_from,
        force=args.force,
    )


def run_async(args: argparse.Namespace) -> int:
    if args.command != "publish":
        raise RuntimeError(f"Unsupported command: {args.command}")
    return asyncio.run(publish_all.run_publish(args.config, build_overrides(args)))


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv) if argv is not None else None)
    try:
        return run_async(args)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
