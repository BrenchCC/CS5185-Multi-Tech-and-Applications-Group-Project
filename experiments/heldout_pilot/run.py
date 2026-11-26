"""Execute the preselected CS5185 held-out experiment from the repository root."""

import os
import sys
import json
import shutil
import logging
from pathlib import Path

sys.path.append(os.getcwd())

from adaptive_encoding.core import GROUPS, Context, sha256, save_json, check_environment
from adaptive_encoding.experiments import create_run, execute_jobs, export_evidence

logger = logging.getLogger(__name__)


def main():
    """Run the three-video matrix with the frozen calibration artifact."""
    dataset = Path("CS5185_Project_Video_Dataset")
    sources = [dataset / name for name in ("05_Jockey.mp4", "06_ShakeNDry.mp4", "09_Parkrun.mp4")]
    policy_path = Path("runs/20261126T075311701182Z_calibration/policy.json")
    if sha256(policy_path) != "31596af38a758e58f12f676b6e6f0d53f51b520886f149148aa365d2e9c313e7":
        raise ValueError("Frozen policy checksum mismatch")
    policy = json.loads(policy_path.read_text())
    folder = create_run("runs", "heldout_pilot")
    print(folder, flush = True)
    shutil.copy2(policy_path, folder / "policy.json")
    shutil.copy2(__file__, folder / "source" / "run.py")
    # 记录实际代码与策略 / Fingerprint snapshot files before encoding.
    files = [folder / "policy.json", *sorted((folder / "source").iterdir())]
    save_json(folder / "checksums.json", {str(p.relative_to(folder)): sha256(p) for p in files})
    context = Context()
    save_json(folder / "input_check.json", check_environment(dataset, context))
    jobs = []
    for source in sources:
        for ratio in (0.05, 0.02):
            strategies = list(GROUPS)
            if source == sources[0] and ratio == 0.02:
                strategies.append("llm")
            for strategy in strategies:
                jobs.append({
                    "name": f"{source.stem}_{ratio}_{strategy}",
                    "source": source,
                    "ratio": ratio,
                    "strategy": strategy,
                    "policy": policy if strategy == "rule" else None,
                })
    execute_jobs(jobs, folder, context)
    export_evidence(folder, ("05", "06", "09"))


if __name__ == "__main__":
    main()
