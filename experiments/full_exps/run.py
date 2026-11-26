"""Preflight or execute the 12-video experiment from the repository root."""

import os
import csv
import sys
import json
import shutil
import logging
import argparse
from pathlib import Path

sys.path.append(os.getcwd())

from adaptive_encoding.core import GROUPS, DEV_IDS, Context, sha256, save_json, check_environment
from adaptive_encoding.experiments import create_run, execute_jobs, export_evidence

logger = logging.getLogger(__name__)
HERE = Path(__file__).resolve().parent


def parse_args():
    """Read the optional execution flag."""
    parser = argparse.ArgumentParser(description = __doc__)
    parser.add_argument("--execute", action = "store_true", help = "Encode the verified matrix")
    return parser.parse_args()


def main():
    """Verify inputs and the frozen matrix, then optionally run every configuration."""
    args = parse_args()
    policy_path = HERE / "policy.json"
    if sha256(policy_path) != "31596af38a758e58f12f676b6e6f0d53f51b520886f149148aa365d2e9c313e7":
        raise ValueError("Frozen policy checksum mismatch")
    policy = json.loads(policy_path.read_text())
    context = Context()
    dataset = Path("CS5185_Project_Video_Dataset")
    report = check_environment(dataset, context)
    tasks, rows, prefixes = [], [], []
    for info in report["inputs"]:
        source = dataset / Path(info["path"]).name
        prefix = source.name[:2]
        prefixes.append(prefix)
        split = "development" if prefix in DEV_IDS else "heldout"
        for pct in (5, 2):
            for strategy in GROUPS:
                rows.append([source.name, split, str(pct), str(info["bytes"] * pct // 100), strategy])
                tasks.append({
                    "name": f"{source.stem}_{pct / 100}_{strategy}",
                    "source": source,
                    "ratio": pct / 100,
                    "strategy": strategy,
                    "policy": policy if strategy == "rule" else None,
                })
    # 核对预登记矩阵 / Match every configuration against the published matrix.
    with (HERE / "matrix.csv").open(newline = "") as handle:
        manifest = list(csv.reader(handle))
    header = ["video", "split", "budget_pct", "target_bytes", "strategy"]
    if prefixes != [f"{n:02}" for n in range(1, 13)] or manifest != [header, *rows]:
        raise ValueError("Dataset or task matrix mismatch")
    print(f"Preflight passed: {len(prefixes)} videos, {len(tasks)} configurations.", flush = True)
    if not args.execute:
        return 0
    folder = create_run("runs", "full_exps")
    print(folder, flush = True)
    for name in ("policy.json", "matrix.csv"):
        shutil.copy2(HERE / name, folder / name)
    shutil.copy2(__file__, folder / "source" / "run.py")
    save_json(folder / "input_check.json", report)
    records = execute_jobs(tasks, folder, context)
    export_evidence(folder, prefixes)
    return int(any(record["status"] != "success" for record in records))


if __name__ == "__main__":
    raise SystemExit(main())
