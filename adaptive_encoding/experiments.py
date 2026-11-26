"""Development-only candidate search, threshold calibration and evidence export."""

import os
import sys
import json
import time
import shutil
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone

import cv2
import matplotlib
import numpy as np
import matplotlib.pyplot as plt

sys.path.append(os.getcwd())

from adaptive_encoding.core import DEV_IDS, GROUPS, CANDIDATES, FEATURE_VERSION
from adaptive_encoding.core import Context, environment, run_task, save_json, summarize, stump_value, check_environment

logger = logging.getLogger(__name__)

matplotlib.use("Agg")


def create_run(root, purpose):
    """Create a unique run under root and save a purpose-specific environment manifest."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    folder = Path(root) / f"{stamp}_{purpose}"
    folder.mkdir(parents = True, exist_ok = False)
    save_json(folder / "manifest.json", {"purpose": purpose, **environment()})
    source_folder = folder / "source"
    source_folder.mkdir()
    for source in [
        Path("main.py"),
        Path("requirements.txt"),
        Path("prompts/encoding_decision_zh.md"),
        Path("utils/json_extract.py"),
        *Path("adaptive_encoding").glob("*.py"),
    ]:
        shutil.copy2(source, source_folder / source.name)
    return folder


def development_paths(dataset):
    """Return the six required development videos found within dataset."""
    paths = sorted(
        path for path in Path(dataset).glob("*.mp4") if path.name[:2] in DEV_IDS
    )
    if len(paths) != 6:
        raise ValueError("Expected all six development videos: 01, 02, 03, 04, 07, 08")
    return paths


def stumps(samples, choices):
    """Enumerate one-threshold and constant rules from measured samples and choices."""
    result = [
        {
            "feature": None,
            "threshold": None,
            "low": choice,
            "high": choice,
        }
        for choice in choices
    ]
    for feature in ("motion_mean", "edge_mean", "bpp"):
        values = sorted(set(sample["values"][feature] for sample in samples))
        for left, right in zip(values, values[1:]):
            for low, high in (choices, choices[::-1]):
                result.append(
                    {
                        "feature": feature,
                        "threshold": (left + right) / 2,
                        "low": low,
                        "high": high,
                    }
                )
    return result


def calibration_samples(records):
    """Group complete candidate records into per-video-budget calibration samples."""
    grouped = {}
    for record in records:
        key = (record["video_id"], record["target_ratio"])
        if "decision_inputs" not in record or "decision" not in record:
            raise ValueError(
                "Calibration cannot freeze: a candidate failed before feature extraction"
            )
        sample = grouped.setdefault(
            key,
            {
                "video_id": key[0],
                "ratio": key[1],
                "values": record["decision_inputs"],
                "candidates": {},
            },
        )
        candidate = (record["decision"]["preset"], record["decision"]["aq_mode"])
        if candidate in sample["candidates"]:
            raise ValueError("Duplicate calibration candidate")
        sample["candidates"][candidate] = record
    samples = list(grouped.values())
    for sample in samples:
        if set(sample["candidates"]) != set(CANDIDATES):
            raise ValueError("Incomplete four-candidate calibration matrix")
        if not any(
            record["status"] == "success" for record in sample["candidates"].values()
        ):
            raise ValueError("No valid calibration candidate for a development target")
    return samples


def choose_rules(samples):
    """Search preset and AQ stumps jointly using quality-first tolerance ordering on samples."""
    preset_rules = stumps(samples, ("medium", "slow"))
    aq_rules = stumps(samples, (1, 2))
    scores = []
    for preset_rule in preset_rules:
        for aq_rule in aq_rules:
            selected = [
                sample["candidates"][
                    (
                        stump_value(preset_rule, sample["values"]),
                        stump_value(aq_rule, sample["values"]),
                    )
                ]
                for sample in samples
            ]
            valid = [record for record in selected if record["status"] == "success"]
            psnr = [
                record["metrics"]["psnr_y_db"]
                if not record["metrics"]["psnr_infinite"]
                else 1000
                for record in valid
            ]
            scores.append(
                {
                    "preset": preset_rule,
                    "aq_mode": aq_rule,
                    "successes": len(valid),
                    "ms_ssim": float(
                        np.mean([record["metrics"]["ms_ssim"] for record in valid])
                    )
                    if valid
                    else -1,
                    "psnr": float(np.mean(psnr)) if valid else -1,
                    "encode_time_s": sum(
                        record["encode_time_s"] for record in selected
                    ),
                    "complexity": int(preset_rule["feature"] is not None)
                    + int(aq_rule["feature"] is not None),
                }
            )
    max_success = max(score["successes"] for score in scores)
    remaining = [score for score in scores if score["successes"] == max_success]
    best_ms = max(score["ms_ssim"] for score in remaining)
    remaining = [score for score in remaining if best_ms - score["ms_ssim"] < 0.0001]
    best_psnr = max(score["psnr"] for score in remaining)
    remaining = [score for score in remaining if best_psnr - score["psnr"] < 0.01]
    # 稳定排序解决完全并列 / Enumeration order resolves exact ties deterministically.
    return min(
        remaining, key = lambda score: (score["encode_time_s"], score["complexity"])
    )


def fit_policy(records):
    """Build frozen threshold rules and video-held-out validation evidence from records."""
    samples = calibration_samples(records)
    held_out = []
    for video_id in sorted(set(sample["video_id"] for sample in samples)):
        train = [sample for sample in samples if sample["video_id"] != video_id]
        if not train:
            raise ValueError(
                "At least two videos are required for leave-one-video-out validation"
            )
        rule = choose_rules(train)
        for sample in (sample for sample in samples if sample["video_id"] == video_id):
            candidate = (
                stump_value(rule["preset"], sample["values"]),
                stump_value(rule["aq_mode"], sample["values"]),
            )
            selected = sample["candidates"][candidate]
            best = max(
                record["metrics"]["ms_ssim"]
                for record in sample["candidates"].values()
                if record["status"] == "success"
            )
            held_out.append(
                {
                    "video_id": video_id,
                    "ratio": sample["ratio"],
                    "selected": list(candidate),
                    "status": selected["status"],
                    "ms_ssim_regret": best - selected["metrics"]["ms_ssim"]
                    if selected["status"] == "success"
                    else None,
                    "preset_rule": rule["preset"],
                    "aq_rule": rule["aq_mode"],
                }
            )
    fitted = choose_rules(samples)
    policy = {
        "feature_version": FEATURE_VERSION,
        "preset": fitted["preset"],
        "aq_mode": fitted["aq_mode"],
        "selection": fitted,
        "development_ids": list(DEV_IDS),
        "input_hashes": {
            record["video_id"]: record["input_sha256"] for record in records
        },
        "objective": "Maximize valid outputs, then mean MS-SSIM (tolerance 0.0001), PSNR (0.01 dB), minimize encoding time, minimize rule complexity",
        "held_out": held_out,
        "limitations": "Six development videos only; thresholds and quality tolerances are empirical engineering choices. Development results do not establish test-set generalization.",
    }
    policy["policy_version"] = hashlib.sha256(
        json.dumps(policy, sort_keys = True).encode()
    ).hexdigest()[:16]
    return policy


def execute_jobs(jobs, folder, context):
    """Run sequential jobs into folder, publishing queue progress through context."""
    records = []
    cancelled = False
    for index, job in enumerate(jobs):
        if context.cancel.is_set():
            cancelled = True
            break
        context.emit(
            "Queue",
            completed = index,
            total = len(jobs),
            video = Path(job["source"]).name,
        )
        arguments = {key: value for key, value in job.items() if key != "name"}
        record = run_task(folder = folder / job["name"], context = context, **arguments)
        records.append(record)
        save_json(
            folder / "queue.json",
            {"completed": index + 1, "total": len(jobs), "status": "running"},
        )
        if record["status"] == "cancelled":
            cancelled = True
            break
    status = (
        "cancelled"
        if cancelled
        else (
            "completed"
            if all(record["status"] == "success" for record in records)
            else "completed_with_failures"
        )
    )
    task_states = [
        {
            "name": job["name"],
            "status": records[index]["status"]
            if index < len(records)
            else "not_started",
        }
        for index, job in enumerate(jobs)
    ]
    save_json(
        folder / "queue.json",
        {
            "completed": len(records),
            "total": len(jobs),
            "status": status,
            "not_started": len(jobs) - len(records),
            "tasks": task_states,
        },
    )
    summarize(folder)
    context.emit(
        "Batch complete",
        completed = len(records),
        total = len(jobs),
        status = status,
    )
    return records


def calibrate(dataset, root, context = None):
    """Execute 48 development candidates from dataset under root using context; freeze policy."""
    context = context or Context()
    folder = create_run(root, "calibration")
    context.emit("Run created", folder = str(folder.resolve()))
    save_json(folder / "input_check.json", check_environment(dataset, context))
    started = time.perf_counter()
    jobs = []
    for source in development_paths(dataset):
        for ratio in (0.05, 0.02):
            for preset, aq in CANDIDATES:
                jobs.append(
                    {
                        "name": f"{source.stem}_{ratio}_{preset}_aq{aq}",
                        "source": source,
                        "ratio": ratio,
                        "strategy": "calibration",
                        "candidate": (preset, aq),
                    }
                )
    records = execute_jobs(jobs, folder, context)
    if context.cancel.is_set():
        return folder
    context.emit("Calibrating thresholds")
    policy = fit_policy(records)
    policy["calibration_run"] = str(folder.resolve())
    policy["calibration_time_s"] = time.perf_counter() - started
    save_json(folder / "policy.json", policy)
    save_json(Path(root) / "policy.json", policy)
    export_evidence(folder)
    return folder


def batch(
    dataset,
    root,
    policy_path,
    context = None
):
    """Validate the frozen policy_path across development videos from dataset under root."""
    context = context or Context()
    policy = json.loads(Path(policy_path).read_text())
    folder = create_run(root, "validation")
    context.emit("Run created", folder = str(folder.resolve()))
    save_json(folder / "policy.json", policy)
    save_json(folder / "input_check.json", check_environment(dataset, context))
    jobs = []
    for source in development_paths(dataset):
        for ratio in (0.05, 0.02):
            for strategy in GROUPS:
                jobs.append(
                    {
                        "name": f"{source.stem}_{ratio}_{strategy}",
                        "source": source,
                        "ratio": ratio,
                        "strategy": strategy,
                        "policy": policy,
                    }
                )
    execute_jobs(jobs, folder, context)
    if not context.cancel.is_set():
        export_evidence(folder)
    return folder


def export_evidence(folder, video_prefixes = ("01", "03", "07")):
    """Export curves under folder and aligned frames for the requested video_prefixes."""
    folder = Path(folder)
    records = summarize(folder)
    evidence = folder / "evidence"
    evidence.mkdir(exist_ok = True)
    for video_id in sorted(set(record["video_id"] for record in records)):
        feature_file = next(folder.glob(f"{video_id}_*/features.json"), None)
        if feature_file is None:
            continue
        measured = json.loads(feature_file.read_text())
        timeline = measured["timeline"]
        figure, axes = plt.subplots(
            2,
            1,
            figsize = (9, 5),
            sharex = True,
        )
        axes[0].plot(
            [row["time_s"] for row in timeline], [row["motion"] for row in timeline]
        )
        axes[0].set_ylabel("Normalized frame MAD")
        axes[1].plot(
            [row["time_s"] for row in timeline], [row["edge"] for row in timeline]
        )
        axes[1].set_ylabel("Edge density")
        axes[1].set_xlabel("Time (s)")
        figure.suptitle(video_id)
        figure.tight_layout()
        figure.savefig(evidence / f"{video_id}_features.png", dpi = 140)
        plt.close(figure)
    for video_prefix in video_prefixes:
        for ratio in (0.05, 0.02):
            selected = [
                record
                for record in records
                if record["video_id"].startswith(video_prefix)
                and record["target_ratio"] == ratio
                and record["strategy"] in GROUPS
            ]
            if len(selected) != 3:
                continue
            reference = selected[0]
            frame_index = reference["input"]["frame_count"] // 2
            panels = [("Original", reference["source_path"], None)] + [
                (record["strategy"], record["output_path"], record["failure_reason"])
                for record in selected
            ]
            figure, axes = plt.subplots(2, 2, figsize = (16, 9))
            for axis, (title, path, failure) in zip(axes.flat, panels):
                if not path:
                    axis.text(0.5, 0.5, failure or "No valid output", ha = "center", wrap = True)
                    axis.set_title(title)
                    axis.axis("off")
                    continue
                video = cv2.VideoCapture(path)
                try:
                    video.set(cv2.CAP_PROP_POS_FRAMES, frame_index)
                    ok, frame = video.read()
                    if not ok:
                        raise ValueError(f"Cannot export aligned frame: {path}")
                    axis.imshow(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                    axis.set_title(f"{title} | frame {frame_index}")
                    axis.axis("off")
                finally:
                    video.release()
            figure.suptitle(
                f"{reference['video_id']} | target {ratio:.0%} | identical frame index"
            )
            figure.tight_layout()
            figure.savefig(
                evidence / f"{reference['video_id']}_{ratio}_comparison.png", dpi = 120
            )
            plt.close(figure)
