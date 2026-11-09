import argparse
import os
import sys
from pathlib import Path

from .config import Config, PipelineError
from .pipeline import create_short


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an English Short for FERNIMOON STUDIO.")
    parser.add_argument("--topic", default=os.environ.get("SHORTS_TOPIC", ""), help="Topic (English or Vietnamese); narration is English")
    parser.add_argument("--duration", type=int, default=60, choices=(30, 45, 60, 75, 90), metavar="{30,45,60,75,90}")
    parser.add_argument("--mode", choices=("documentary", "football"),
                        default=os.environ.get("FERNIMOON_MODE", "documentary"),
                        help="Production mode: documentary or global football")
    parser.add_argument("--date", default=os.environ.get("FOOTBALL_DATE", ""),
                        help="Football match date in YYYY-MM-DD format; defaults to today")
    parser.add_argument("--format", default=os.environ.get("FOOTBALL_FORMAT", "auto"),
                        choices=("auto", "global_roundup", "breaking_news", "transfer_watch",
                                 "match_preview", "match_recap", "tactical_analysis",
                                 "player_spotlight", "club_business", "drama", "academy", "history_facts"),
                        help="Football editorial format")
    parser.add_argument("--output", type=Path, default=Path("output/fernimoon"))
    args = parser.parse_args()
    try:
        config = Config.from_env(args.duration, args.mode, args.format)
        create_short(args.topic, config, args.output, match_date=args.date or None, editorial_format=args.format)
        return 0
    except PipelineError as exc:
        print(f"FERNIMOON: {exc}", file=sys.stderr)
        return 1
    except (OSError, ValueError, TypeError, KeyError):
        # Do not print raw provider objects, environment values or HTTP URLs with secrets.
        print("FERNIMOON: invalid provider data or local filesystem failure. Check configuration and retry.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
