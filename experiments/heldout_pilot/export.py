"""Export the two report tables and a portable audit bundle from a finished pilot."""

import csv
import sys
import json
import shutil
import zipfile
import logging
import hashlib
from pathlib import Path

logger = logging.getLogger(__name__)


def read(path):
    """Load one UTF-8 JSON file from path."""
    return json.loads(path.read_text(encoding = "utf-8"))


def checksum(path):
    """Hash the binary file at path."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_table(path, rows):
    """Write rows with consistent keys as a UTF-8 CSV at path."""
    with path.open("w", newline = "", encoding = "utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames = list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def export(folder):
    """Check the completed pilot in folder and export report evidence beside this script."""
    destination = Path(__file__).resolve().parent
    queue = read(folder / "queue.json")
    expected = {
        (video, ratio, strategy)
        for video in ("05_Jockey", "06_ShakeNDry", "09_Parkrun")
        for ratio in (0.05, 0.02)
        for strategy in ("baseline_medium", "baseline_slow", "rule")
    }
    expected.add(("05_Jockey", 0.02, "llm"))
    assert queue["completed"] == queue["total"] == len(expected)
    assert queue["status"] in ("completed", "completed_with_failures")
    for name, digest in read(folder / "checksums.json").items():
        assert checksum(folder / name) == digest
    tasks, rounds = [], []
    for path in sorted(folder.glob("*/task.json")):
        record = read(path)
        key = (record["video_id"], record["target_ratio"], record["strategy"])
        expected.remove(key)
        source = Path(record["source_path"])
        meta = read(source.parent / "metadata" / (source.stem + ".json"))
        assert checksum(source) == record["input_sha256"] == meta["sha256"]
        target = record["target_bytes"]
        ratio_pct = round(100 * record["target_ratio"])
        assert target == source.stat().st_size * ratio_pct // 100
        features = read(path.parent / "features.json")
        assert len(features["timeline"]) == record["input"]["frame_count"]
        attempts = record["attempts"]
        assert 1 <= len(attempts) <= 3
        decision = record.get("decision", {})
        metrics = record.get("metrics") or {}
        actual = record.get("actual_bytes")
        # 与输出文件和逐轮记录交叉核验 / Reconcile summaries against actual files.
        if record["status"] == "success":
            output = Path(record["output_path"])
            assert actual == output.stat().st_size and actual <= target
            assert checksum(output) == record["output_sha256"]
            assert metrics["decode_ok"] and metrics["frame_count"] == len(metrics["per_frame_ms_ssim"])
            assert metrics["frame_count"] == record["input"]["frame_count"]
            assert attempts[-1]["metrics"] == metrics and actual == attempts[-1]["actual_bytes"]
        common = {"video_id": key[0], "budget_pct": ratio_pct, "strategy": key[2]}
        tasks.append({
            **common,
            "status": record["status"],
            "target_bytes": target,
            "actual_bytes": actual,
            "budget_used_pct": 100 * actual / target if actual else None,
            "target_file_bps": 8 * target / record["input"]["duration_s"],
            "target_video_bps": record["initial_video_bps"],
            "actual_file_bps": metrics.get("file_bitrate_bps"),
            "actual_video_bps": metrics.get("video_bitrate_bps"),
            **record["decision_inputs"],
            "preset": decision.get("preset"),
            "aq_mode": decision.get("aq_mode"),
            "psnr_y_db": metrics.get("psnr_y_db"),
            "ms_ssim_y": metrics.get("ms_ssim"),
            "frames": metrics.get("frame_count"),
            "duration_s": metrics.get("duration_s"),
            "decode_ok": metrics.get("decode_ok"),
            "feature_s": record["feature_time_s"],
            "decision_s": record["decision_time_s"],
            "ark_s": record["agent_time_s"],
            "encode_s": record["encode_time_s"],
            "evaluate_s": record["eval_time_s"],
            "total_s": record["total_time_s"],
            "attempts": len(attempts),
            "api_calls": sum("request" in a.get("llm", {}) for a in attempts),
            "failure_reason": record["failure_reason"],
            "task_json": path.as_posix(),
        })
        for a in attempts:
            directory = path.parent / f"attempt_{a['number']}"
            detail = directory / "attempt.json"
            assert read(detail) == a
            if a.get("actual_bytes"):
                assert a["return_codes"] == [0, 0]
                assert a["actual_bytes"] == (directory / "output.mp4").stat().st_size
            choice = a.get("decision", {})
            audit = a.get("llm", {})
            rounds.append({
                **common,
                "attempt": a["number"],
                "controller": a["controller"],
                "preset": choice.get("preset"),
                "aq_mode": choice.get("aq_mode"),
                "reason": choice.get("reason"),
                "target_video_bps": a["bitrate_bps"],
                "target_bytes": target,
                "actual_bytes": a.get("actual_bytes"),
                "bytes_remaining": target - a["actual_bytes"] if "actual_bytes" in a else None,
                "status": a["status"],
                "psnr_y_db": (a.get("metrics") or {}).get("psnr_y_db"),
                "ms_ssim_y": (a.get("metrics") or {}).get("ms_ssim"),
                "pass_1_s": next(iter(a["pass_times_s"]), None),
                "pass_2_s": a["pass_times_s"][1] if len(a["pass_times_s"]) == 2 else None,
                "next_action": "stop" if a == attempts[-1] else "retry",
                "next_video_bps": a.get("next_bitrate_bps"),
                "adjustment_or_error": a.get("adjustment_reason") or a.get("failure_reason"),
                "prompt_tokens": audit.get("prompt_tokens"),
                "completion_tokens": audit.get("completion_tokens"),
                "attempt_json": detail.as_posix(),
                "pass_logs": " | ".join(p.as_posix() for p in sorted(directory.glob("pass_*.log"))),
            })
    assert not expected
    assert sum(t["api_calls"] for t in tasks) <= 3
    write_table(destination / "tasks.csv", tasks)
    write_table(destination / "attempts.csv", rounds)
    shutil.copytree(folder / "evidence", destination / "figures", dirs_exist_ok = True)
    # 保留原目录布局，排除视频 / Preserve audit paths without redistributing videos.
    with zipfile.ZipFile(destination / "records.zip", "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(folder / "policy.json", "runs/20261126T075311701182Z_calibration/policy.json")
        for path in sorted(folder.rglob("*")):
            if path.is_file() and (path.suffix in (".json", ".py", ".md", ".txt") or path.name in ("pass_1.log", "pass_2.log")):
                archive.write(path)


if __name__ == "__main__":
    export(Path(sys.argv[1]))
