"""Run a small fixed-baseline demo; requires FFmpeg and ffprobe on PATH."""

import os
import sys
import csv
import json
import time
import logging
import argparse
import subprocess
from pathlib import Path
from fractions import Fraction
from datetime import datetime

import cv2
import numpy as np
from tqdm import tqdm
from dotenv import load_dotenv

sys.path.append(os.getcwd())

from utils.ark_llm_call import call_llm_on_volcengine

logger = logging.getLogger(__name__)
ROOT = Path(__file__).resolve().parent


def parse_args():
    """Parse the input video, budget ratio, and output directory arguments."""
    parser = argparse.ArgumentParser(description = "单视频双遍压缩示例（默认固定参数，可选 --llm）")
    parser.add_argument("--input", type = Path, default = ROOT / "CS5185_Project_Video_Dataset/01_FourPeople.mp4")
    parser.add_argument("--ratio", type = float, choices = [0.05, 0.02], default = 0.05)
    parser.add_argument("--output-dir", type = Path, default = ROOT / "outputs/demo")
    parser.add_argument("--llm", action = "store_true", help = "调用文本 LLM 选择 preset 和 AQ")
    return parser.parse_args()


def run(command, log_path):
    """Run command as an argument list and save stderr to log_path."""
    with log_path.open("w") as log_file:
        result = subprocess.run(command, stdout = subprocess.PIPE, stderr = log_file)
    if result.returncode:
        raise RuntimeError(f"命令失败，详见 {log_path}")
    return result.stdout


def probe(path):
    """Read video stream metadata and every decoded frame timestamp from path."""
    command = [
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_streams", "-show_frames", "-show_entries",
        "stream=width,height,avg_frame_rate,duration:frame=best_effort_timestamp_time",
        "-of", "json", str(path)
    ]
    result = subprocess.run(command, capture_output = True, check = True)
    data = json.loads(result.stdout)
    stream = data["streams"][0]
    return {
        "width": stream["width"],
        "height": stream["height"],
        "fps": stream["avg_frame_rate"],
        "duration_s": float(stream["duration"]),
        "timestamps": [float(frame["best_effort_timestamp_time"]) for frame in data["frames"]]
    }


def analyze_video(path, timestamps, csv_path):
    """Analyze path using aligned timestamps and save per-frame values to csv_path.

    Args:
        path: Video file to decode with OpenCV.
        timestamps: Validated frame timestamps from ffprobe, in seconds.
        csv_path: Destination for frame brightness, contrast, edges, and differences.
    """
    capture = cv2.VideoCapture(str(path))
    if not capture.isOpened():
        raise RuntimeError(f"OpenCV 无法打开视频：{path}")
    rows = []
    previous = None
    try:
        for index in tqdm(range(len(timestamps)), desc = f"分析 {path.name}"):
            ok, frame = capture.read()
            if not ok:
                raise RuntimeError(f"OpenCV 在第 {index} 帧提前结束：{path}")
            # 原始分辨率逐帧灰度分析。 / Analyze every frame at native resolution.
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            edges = cv2.Canny(gray, 100, 200)
            # 首帧没有前帧，保留空值；absdiff 避免 uint8 减法溢出。
            # Leave first difference missing; absdiff avoids unsigned wraparound.
            difference = None if previous is None else float(np.mean(cv2.absdiff(gray, previous)) / 255)
            rows.append({
                "frame_index": index,
                "timestamp_s": timestamps[index],
                "brightness_mean": float(np.mean(gray)),
                "brightness_std": float(np.std(gray)),
                "edge_density": float(np.count_nonzero(edges) / edges.size),
                "frame_difference": difference
            })
            previous = gray
        if capture.read()[0]:
            raise RuntimeError(f"OpenCV 帧数超出 ffprobe 记录：{path}")
    finally:
        capture.release()
    with csv_path.open("w", newline = "") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames = list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = {}
    for key in ("brightness_mean", "brightness_std", "edge_density", "frame_difference"):
        values = np.asarray([row[key] for row in rows if row[key] is not None])
        summary[key] = {
            "count": int(values.size),
            "mean": float(np.mean(values)) if values.size else None,
            "p95": float(np.percentile(values, 95)) if values.size else None,
            "max": float(np.max(values)) if values.size else None
        }
    logger.info("%s 内容特征：%s", path.name, summary)
    return {"frame_count": len(rows), "timeline_csv": str(csv_path), "summary": summary}


def choose_with_llm(features, budget, log_path):
    """Choose parameters from features and budget, saving redacted calls to log_path."""
    load_dotenv(ROOT / ".env")
    endpoint = os.environ.get("LLM_ENDPOINT")
    system_prompt = (
        '根据实测灰度特征和预算选择 x264 参数。只返回 JSON：'
        '{"preset":"medium或slow","aq_mode":1或2,"reason":"基于特征的中文理由"}。'
        '不得选择其他参数。特征不等同于物体运动或画质，选择不保证优于固定基线。'
    )
    query = json.dumps({"features": features, "budget": budget}, ensure_ascii = False)
    secret = os.environ.get("LLM_API_KEY", "")
    for attempt in range(1, 3):
        record = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "attempt": attempt,
            "model": endpoint,
            "system_prompt": system_prompt,
            "input_query": query
        }
        started = time.perf_counter()
        decision = None
        try:
            if not endpoint:
                raise ValueError("Missing LLM_ENDPOINT")
            reasoning, response, prompt_tokens, completion_tokens = call_llm_on_volcengine(
                query, endpoint, system_prompt = system_prompt
            )
            record.update({
                "response": response,
                "reasoning": reasoning,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens
            })
            decision = json.loads(response)
            if not isinstance(decision, dict):
                raise ValueError("Response must be a JSON object")
            if decision.get("preset") not in ("medium", "slow"):
                raise ValueError("Invalid preset")
            if type(decision.get("aq_mode")) is not int or decision["aq_mode"] not in (1, 2):
                raise ValueError("Invalid aq_mode")
            if not isinstance(decision.get("reason"), str) or not decision["reason"].strip():
                raise ValueError("Missing reason")
            decision = {key: decision[key] for key in ("preset", "aq_mode", "reason")}
            record["status"] = "valid"
        except Exception as error:
            decision = None
            record.update({"status": "failed", "error_type": type(error).__name__, "error": str(error)})
            logger.warning("LLM 第 %s 次调用失败：%s（详见调用记录）", attempt, type(error).__name__)
        finally:
            record["elapsed_seconds"] = time.perf_counter() - started
            serialized = json.dumps(record, ensure_ascii = False)
            if secret:
                serialized = serialized.replace(secret, "[REDACTED]")
            with log_path.open("a") as log_file:
                log_file.write(serialized + "\n")
        if decision is not None:
            return {**decision, "method": "llm", "log": str(log_path)}
    return {
        "preset": "medium",
        "aq_mode": 1,
        "reason": "LLM 调用或响应验证连续失败，使用固定参数回退；详见调用记录",
        "method": "fallback",
        "log": str(log_path)
    }


def main():
    """Encode one source with at most three attempts and save verified results."""
    args = parse_args()
    started = time.perf_counter()
    source = args.input.resolve(strict = True)
    # 每次运行创建独立目录，保留先前结果。 / Isolate runs and pass logs.
    args.output_dir.mkdir(parents = True, exist_ok = True)
    output_dir = args.output_dir / datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    output_dir.mkdir()
    report_path = output_dir / "result.json"
    report = {"status": "running", "input": str(source), "attempts": []}
    try:
        reference = probe(source)
        analysis_started = time.perf_counter()
        report["analysis_method"] = {
            "opencv_version": cv2.__version__,
            "numpy_version": np.__version__,
            "sampling": "every frame, native resolution, cvtColor BGR2GRAY (uint8)",
            "brightness_mean": "mean gray value, range 0..255",
            "brightness_std": "population standard deviation of gray pixels, ddof=0",
            "edge_density": "fraction of nonzero Canny pixels; thresholds=100,200; apertureSize=3; L2gradient=False",
            "frame_difference": "mean absolute gray difference / 255; first frame excluded",
            "aggregation": "temporal mean, 95th percentile (linear), maximum; equal frame weights",
            "interpretation": "descriptive features, not motion estimates or quality scores"
        }
        report["source_analysis"] = analyze_video(source, reference["timestamps"], output_dir / "source_features.csv")
        report["analysis_seconds"] = time.perf_counter() - analysis_started
        source_bytes = source.stat().st_size
        target_bytes = int(source_bytes * args.ratio)
        bitrate = int(0.98 * 8 * target_bytes / reference["duration_s"])
        decision = {"preset": "medium", "aq_mode": 1, "method": "fixed_baseline_no_llm"}
        if args.llm:
            llm_started = time.perf_counter()
            decision = choose_with_llm(
                report["source_analysis"]["summary"],
                {"target_bytes": target_bytes, "target_ratio": args.ratio, "duration_s": reference["duration_s"]},
                output_dir / "llm_calls.jsonl"
            )
            report["llm_seconds"] = time.perf_counter() - llm_started
            logger.info("LLM 决策：%s", decision["method"])
        report.update({
            "source_bytes": source_bytes,
            "target_ratio": args.ratio,
            "target_bytes": target_bytes,
            "preset": decision["preset"],
            "aq_mode": decision["aq_mode"],
            "decision": decision,
            "quality_metrics": "not_measured",
            "reference": reference
        })
        logger.info("输入 %s，目标 %s 字节（%.0f%%）", source.name, target_bytes, args.ratio * 100)
        for attempt in range(1, 4):
            logger.info("第 %s 次双遍编码，码率 %s bit/s", attempt, bitrate)
            output = output_dir / f"attempt_{attempt}.mp4"
            pass_log = output_dir / f"pass_{attempt}"
            record = {"attempt": attempt, "video_bps": bitrate, "commands": []}
            report["attempts"].append(record)
            encode_started = time.perf_counter()
            for pass_number in (1, 2):
                command = [
                    "ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-n",
                    "-i", str(source), "-map", "0:v:0", "-an",
                    "-c:v", "libx264", "-preset", decision["preset"], "-pix_fmt", "yuv420p",
                    "-b:v", str(bitrate), "-x264-params", f"aq-mode={decision['aq_mode']}",
                    "-pass", str(pass_number), "-passlogfile", str(pass_log)
                ]
                command += ["-f", "null", os.devnull] if pass_number == 1 else [str(output)]
                record["commands"].append(command)
                run(command, output_dir / f"attempt_{attempt}_pass_{pass_number}.log")
            record["encoding_seconds"] = time.perf_counter() - encode_started
            # 完整解码并核对时间线，不以共有前缀代替完整性。 / Check the entire output.
            run([
                "ffmpeg", "-v", "error", "-xerror", "-nostdin", "-i", str(output),
                "-map", "0:v:0", "-f", "null", os.devnull
            ], output_dir / f"attempt_{attempt}_decode.log")
            actual = probe(output)
            aligned = (
                actual["width"] == reference["width"]
                and actual["height"] == reference["height"]
                and Fraction(actual["fps"]) == Fraction(reference["fps"])
                and abs(actual["duration_s"] - reference["duration_s"]) <= 0.00001
                and len(actual["timestamps"]) == len(reference["timestamps"])
                and all(abs(a - b) <= 0.00001 for a, b in zip(actual["timestamps"], reference["timestamps"]))
            )
            record.update({"output": str(output), "actual_bytes": output.stat().st_size, "integrity_ok": aligned})
            if not aligned:
                raise RuntimeError("输出完整性检查失败")
            if record["actual_bytes"] <= target_bytes:
                analysis_started = time.perf_counter()
                report["output_analysis"] = analyze_video(output, actual["timestamps"], output_dir / "output_features.csv")
                report["analysis_seconds"] += time.perf_counter() - analysis_started
                report.update({"status": "success", "output": str(output), "actual": actual})
                logger.info("成功：%s 字节，%s 帧；输出 %s", record["actual_bytes"], len(actual["timestamps"]), output)
                break
            record["retry_reason"] = "over_budget"
            bitrate = int(bitrate * target_bytes / record["actual_bytes"] * 0.98)
        else:
            raise RuntimeError("三次尝试后仍超预算")
    except Exception as error:
        report.update({"status": "failed", "error": str(error)})
        raise
    finally:
        report["elapsed_seconds"] = time.perf_counter() - started
        report_path.write_text(json.dumps(report, ensure_ascii = False, indent = 2) + "\n")
        logger.info("运行记录：%s", report_path)


if __name__ == "__main__":
    logging.basicConfig(
        level = logging.INFO,
        format = '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers = [logging.StreamHandler()]
    )
    main()
