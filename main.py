"""Launch the English terminal UI or run reproducible automation commands."""

import os
import sys
import json
import signal
import logging
import argparse
from pathlib import Path



sys.path.append(os.getcwd())

from adaptive_encoding.experiments import create_run, calibrate, batch
from adaptive_encoding.core import Context, check_environment, run_task, save_json, summarize

logger = logging.getLogger(__name__)


def parse_args():
    """Parse optional automation commands; no command launches the terminal UI."""
    parser = argparse.ArgumentParser(
        description = "Content-adaptive x264 encoding laboratory"
    )
    parser.add_argument(
        "command",
        nargs = "?",
        choices = [
            "check",
            "calibrate",
            "run",
            "batch",
            "summarize",
        ],
    )
    parser.add_argument("--dataset", default = "CS5185_Project_Video_Dataset")
    parser.add_argument("--output", default = "runs")
    parser.add_argument("--input")
    parser.add_argument(
        "--ratio",
        type = float,
        choices = [0.05, 0.02],
        default = 0.05,
    )
    parser.add_argument(
        "--strategy",
        choices = [
            "baseline_medium",
            "baseline_slow",
            "rule",
            "llm",
            "hybrid",
        ],
        default = "hybrid",
    )
    parser.add_argument("--policy", default = "runs/policy.json")
    parser.add_argument("--folder", help = "Existing run folder to summarize")
    return parser.parse_args()


def main():
    """Start the interactive UI or execute a selected automation command."""
    args = parse_args()
    if args.command is None:
        from adaptive_encoding.tui import EncoderApp

        EncoderApp(args.dataset, args.output).run()
        return 0
    context = Context(
        callback = lambda event: logger.info(
            "%s",
            {
                key: value
                for key, value in event.items()
                if key not in ("result", "progress")
            },
        )
    )
    signal.signal(signal.SIGINT, lambda *_: context.cancel.set())
    if args.command == "check":
        report = check_environment(args.dataset, context)
        folder = create_run(args.output, "check")
        save_json(folder / "input_check.json", report)
        print(folder)
    elif args.command == "calibrate":
        print(calibrate(args.dataset, args.output, context))
    elif args.command == "batch":
        folder = batch(
            args.dataset,
            args.output,
            args.policy,
            context,
        )
        print(folder)
        state = json.loads((folder / "queue.json").read_text())
        if state["status"] == "completed_with_failures":
            return 1
    elif args.command == "summarize":
        if not args.folder:
            raise ValueError("--folder is required for summarize")
        summarize(args.folder)
        print(Path(args.folder) / "summary.csv")
    elif args.command == "run":
        if not args.input:
            raise ValueError("--input is required for run")
        policy = (
            json.loads(Path(args.policy).read_text())
            if args.strategy in ("rule", "hybrid")
            else None
        )
        folder = create_run(args.output, "single")
        result = run_task(
            args.input,
            args.ratio,
            args.strategy,
            folder / "task",
            context,
            policy,
        )
        summarize(folder)
        print(folder)
        return 0 if result["status"] == "success" else 1
    return 130 if context.cancel.is_set() else 0


if __name__ == "__main__":
    logging.basicConfig(
        level = logging.INFO,
        format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        handlers = [logging.StreamHandler()],
    )
    raise SystemExit(main())
