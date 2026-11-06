import argparse
import os
import sys
from pathlib import Path

from .config import Config, PipelineError
from .pipeline import create_short


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an English, real-footage Short for FERNIMOON STUDIO.")
    parser.add_argument("--topic", default=os.environ.get("SHORTS_TOPIC", ""), help="Topic (English or Vietnamese); narration is English")
    parser.add_argument("--duration", type=int, default=40, choices=range(35, 46), metavar="35–45")
    parser.add_argument("--output", type=Path, default=Path("output/fernimoon"))
    args = parser.parse_args()
    try:
        create_short(args.topic, Config.from_env(args.duration), args.output)
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
