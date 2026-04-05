# CS5185 Implementation and Dataset Appendix

Language: English. [中文](Implementation_and_Dataset_ZH.md) · [Project description](Project_Description_EN.md)

Sources: [CS5185_Implementation_Appendix.pdf](../Group-Project/CS5185_Implementation_Appendix.pdf), pp. 1–6; [Project_Introduction.pptx](../Group-Project/Project_Introduction.pptx), especially slides 9–12; all files under the [video dataset](../Group-Project/CS5185_Project_Video_Dataset). Sections A–F reconstruct the implementation notes; G–H extract the local dataset and license files. The appendix is **optional implementation guidance**, supplementing the brief without replacing its requirements. Code examples are documentary examples and were not executed as a project implementation.

## A. Suggested workflow

Figure A1 is transcribed below in execution order:

1. Read metadata and set the budget.
2. Extract content features.
3. Choose and validate settings.
4. Encode the original input.
5. Measure size, decoding, quality, and time.
6. Decide whether a retry is useful and attempts remain. If yes, use trial feedback and return to step 3.
7. Otherwise, select the best valid candidate or record failure.
8. Save the final output and logs.

Retain valid candidates after each attempt so a later failure does not discard an earlier usable result. A simple starting policy allows **three attempts in total**. Two-pass encoding counts as one attempt, but both passes contribute to runtime. Stop early if another attempt is unlikely to help.

## B. Setup and size control

### B1. Minimal environment

Use NumPy and OpenCV for features, Matplotlib for plots, and Python standard modules `subprocess`, `json`, `csv`, `pathlib`, `time`, and `hashlib` for orchestration. Requests is optional for model APIs.

The PDF gives these Windows virtual-environment commands:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install numpy opencv-python matplotlib
.\.venv\Scripts\python.exe -m pip freeze > requirements.txt
```

Install FFmpeg and ffprobe separately. Add their `bin` folder to Path or configure absolute paths. Verify the build:

```bash
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -h encoder=libx264
```

### B2. Calculate and adjust bitrate

Let `S` be original bytes, `r` the target ratio, and `T` duration in seconds. Round only to whole bytes, never whole MB. The 2% overhead margin is a starting estimate.

```python
target_bytes = floor(S * r)
video_bps = 0.98 * 8 * target_bytes / T
# If an output is too large / 输出超出预算时：
next_video_bps = video_bps * target_bytes / actual_bytes * 0.98
```

This is the source's calculation fragment, not a standalone program; `floor` and the variables need definitions. Use decimal units: **1 MB = 1,000,000 bytes; 1 kbps = 1,000 bit/s**. Re-encode the original input after an adjustment.

### B3. Two-pass example

Replace `INPUT`, `RATEk`, `JOB`, and `OUT.mp4`. Use a unique `JOB` prefix for each attempt and the same prefix for both passes. Each command is one line; the line breaks in the source PDF were only for display.

```bash
ffmpeg -y -i INPUT -an -c:v libx264 -preset medium -pix_fmt yuv420p -b:v RATEk -pass 1 -passlogfile JOB -f null NUL
ffmpeg -y -i INPUT -an -c:v libx264 -preset medium -pix_fmt yuv420p -b:v RATEk -pass 2 -passlogfile JOB -movflags +faststart OUT.mp4
```

In Python, pass an argument list to `subprocess`. On macOS/Linux, replace `NUL` with `/dev/null`. Keep distinct output paths so candidates do not overwrite each other.

### B4. Decode check

```bash
ffmpeg -v error -xerror -i OUT.mp4 -map 0:v:0 -f null NUL
```

Use `/dev/null` on macOS/Linux. Check return code, duration, frame count, and timestamps. This validates decoding without saving reconstructed frames.

## C. Encoder settings and first features

Start with bitrate control and one content-dependent choice. Keep other settings at their preset defaults until there is a reason to test them. These are examples, not required configurations.

| Option | Purpose and starting guidance |
| --- | --- |
| `-c:v libx264` | Selects x264; it is not a quality level. |
| `-b:v` | Target average bitrate, e.g. `2000k` = 2 Mbps. Check actual size. |
| `-pass 1` / `-pass 2` | Analyze first, then allocate bits using saved statistics. Both passes read the original input. |
| `-crf` | Quality-oriented alternative. Lower values usually improve quality and increase size; size is not guaranteed. |
| `-preset` | Search effort. Compare `medium` and `slow`; record quality and runtime. |
| `-g` | Maximum keyframe interval in frames. At 30 fps, 60 is about two seconds. Candidates: 30, 60, 120. |
| `-keyint_min` | Minimum keyframe interval control, subject to x264 rules. Initially leave at default. |
| `-sc_threshold` | Scene-cut sensitivity; higher generally inserts cuts more readily; 0 disables detection. It is not a percentage. |
| `-bf` | Maximum consecutive B-frames. Candidates: 0, 2, 3. More prediction can add reordering delay. |
| `-refs` | Reference-frame count. Candidates: 1, 3, 5. More references cost time and memory. |
| `-aq-mode` | Regional quantization: 0 off; 1 variance-based; 2 automatic variance-based; 3 with dark-region bias. Start with 1 versus 2. |
| `-aq-strength` | AQ strength. Try 0.8, 1.0, 1.2 with the same mode; inspect regional trade-offs. |

Mean absolute grayscale frame difference gives a rough temporal-change signal. Edge-pixel fraction gives a rough detail signal. Camera motion, lighting, and noise affect both. Inspect a timeline before choosing thresholds.

A small decision space is easier to interpret: choose between two presets or two AQ modes, then compare size, quality, and cost.

## D. Optional settings and model interface

### D1. Additional encoder options

| Option | Purpose and starting guidance |
| --- | --- |
| `-me_method` | Motion search, e.g. `hex` or `umh`. More extensive search may improve prediction at extra cost. |
| `-subq` | Subpixel and decision refinement; example values 5, 7, 9. Higher generally costs more time. |
| `-rc-lookahead` | Frames examined ahead for planning. Compare 20 and 40 only if useful for these short clips. |
| `-mbtree` | Uses future prediction importance in bit allocation. Initially keep enabled. |
| `-tune` | Bundled content-specific adjustments, e.g. `film` or `animation`. Begin without an override. |
| `-psy-rd` | Psychovisual optimization, e.g. `1.0:0.0`. Texture preservation can trade against pixel-error metrics. |
| `-deblock` | Deblocking offsets, e.g. `0:0`, `1:1`, `-1:-1`. Strong filtering can reduce block edges but soften detail. |
| `-maxrate` / `-bufsize` | VBV rate/buffer constraints. `bufsize` is bits, not bit/s. Neither guarantees final file size. |
| `-x264-params` | Several x264 options, e.g. `"aq-mode=2:aq-strength=1.0"`. Avoid duplicating settings through other options. |

### D2. Optional LLM interface

Send compact feature summaries, budget, allowed choices, trial history, and remaining attempts. A structured response may be as small as:

```json
{
  "video_kbps": 2000,
  "preset": "medium",
  "aq_mode": 2,
  "reason": "Test regional allocation against the previous candidate."
}
```

Validate fields and ranges before execution. Use a timeout, bounded retries, and a rule-based fallback. Keep keys in environment variables and out of logs. Record provider and model ID. Numbers above illustrate a schema, not universal settings. Check provider availability and limits directly. No particular model is required; a rule-only controller can use the same validation/logging interface.

### D3. DeepSeek teaching example from PPT slides 9–12

These are **historical slide contents**. Speaker notes for slides 9–11 date checks or captures to **27 October 2026**. The links and sample model ID below are reproduced from the slides, without a current online/API check.

1. Sign in to [the API platform](https://platform.deepseek.com). Slide 10 shows the public [sign-in page](https://platform.deepseek.com/sign_in): new users use the registration link next to “Forgot password”; existing users enter account details and click the black “Log in” button. Its notes state no personal account data is included.
2. Open [API keys](https://platform.deepseek.com/api_keys), create a key, copy it for local use, and check balance/usage. The slide 11 screenshot shows Usage, API keys, Recharge, Bills, usage by key, and “Create API key.” Screenshot text states keys are only visible/copyable when created, should not be shared or exposed in browsers/client code, and publicly exposed keys may be disabled. It also says pre-25-April-2024 key usage is not tracked and gives a 200-key account limit; these are screenshot statements, not current limits. Speaker notes describe a documentation screenshot with a red annotation; the actual embedded image shows the API key page.
3. Copy a current model ID from [the documentation](https://api-docs.deepseek.com/).
4. Keep key, base URL, and model ID matched to the provider. The slide gives base URL `https://api.deepseek.com`.

Slide 12 contains only an image. Its heading is “Invoke The Chat API.” It describes an OpenAI API-format example, with non-streaming output by default and `stream = true` for streaming; it refers to Anthropic API examples separately. The visible tabs are curl, python, and nodejs, with Python selected. The image's install instruction is `pip3 install openai`. The code below transcribes it with spacing normalized:

```python
# Please install OpenAI SDK first / 请先安装 OpenAI SDK：pip3 install openai
import os

from openai import OpenAI

client = OpenAI(
    api_key = os.environ.get('DEEPSEEK_API_KEY'),
    base_url = "https://api.deepseek.com",
)

response = client.chat.completions.create(
    model = "deepseek-flash",
    messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello"},
    ],
    stream = False,
    reasoning_effort = "high",
    extra_body = {"thinking": {"type": "enabled"}},
)

print(response.choices[0].message.content)
```

## E. Measurements and reproducibility

### E1. Consistent measurement

Align reference/output frames by timestamp. Do not silently compare only a shared prefix. For a simple evaluation, keep input resolution and frame rate; otherwise document alignment and resampling.

For luma PSNR, aggregate squared errors over all corresponding pixels and frames before taking the logarithm. Record exact matches as infinite PSNR. For MS-SSIM, record implementation, channel, data range, scales, and temporal aggregation. FFmpeg's ordinary `ssim` filter is single-scale.

```python
file_bitrate_bps = 8 * actual_file_bytes / duration_s
video_bitrate_bps = 8 * sum(video_packet_bytes) / duration_s
```

Use ffprobe packet sizes for the second quantity. Whole-file bitrate includes container overhead; keep these columns separate.

### E2. Timing and logs

Measure elapsed time with `time.perf_counter()`, from before metadata reading until after final evaluation and logging. Include all attempts, both passes, API waits, and failures. Exclude installation, downloads, manual development, and report writing. Do not sum overlapping stages as if sequential.

| Record | Suggested fields |
| --- | --- |
| Task summary | `video_id`, `target_ratio`, `target_bytes`, `actual_bytes`, `output_path`, `status`, `failure_reason` |
| Quality and integrity | `psnr_y_db`, `ms_ssim`, `decode_ok`, `duration_s`, `frame_count`, `actual_video_kbps` |
| Timing and selection | `total_time_s`, `encode_time_s`, `agent_time_s`, `eval_time_s`, `attempts`, `selected_attempt` |
| Attempt log | `job_id`, `attempt_id`, features, parameters, FFmpeg arguments, return code, measurements, next action, reason |

Record hardware, software versions, thread count, and caching policy once in run configuration. Hash input and output files for traceability. Preserve full numerical precision in raw logs.

### E3. Checks before batch testing

Check reference self-comparison, deliberately trigger one over-budget retry, and simulate an invalid model response if using an API. Keep debugging cases separate from formal results.

## F. Resource links from the implementation PDF

The source recommends documentation matching the installed version. Links are extracted from the local PDF and have not been refreshed online.

| Category | Resource |
| --- | --- |
| Installation | [Python downloads](https://www.python.org/downloads/) |
| Installation | [Python virtual environments](https://docs.python.org/3/library/venv.html) |
| Installation | [FFmpeg downloads](https://ffmpeg.org/download.html) |
| Analysis | [OpenCV Python](https://pypi.org/project/opencv-python/) |
| Encoding | [FFmpeg libx264 options](https://ffmpeg.org/ffmpeg-codecs.html#libx264_002c-libx264rgb) |
| Metadata | [FFprobe metadata and packets](https://ffmpeg.org/ffprobe.html) |
| Quality | [FFmpeg PSNR filter](https://ffmpeg.org/ffmpeg-filters.html#psnr) |
| Quality | [PyTorch MS-SSIM](https://pypi.org/project/pytorch-msssim/) |
| Optional API | [DeepSeek](https://api-docs.deepseek.com/) |
| Optional API | [SiliconFlow](https://docs.siliconflow.cn/) |
| Optional API | [OpenRouter](https://openrouter.ai/docs/quickstart) |
| Optional API | [Groq](https://console.groq.com/docs/overview) |

Model APIs are optional. Check current model IDs, pricing, access conditions, and rate limits before use. For MS-SSIM, record package version and metric configuration.

## G. Dataset extraction

### G1. Inventory and preview

The dataset contains 12 MP4 files, 12 metadata JSON files, nine license/source text files, and one preview image. The videos are silent visual material; this extraction provides original links, preview descriptions, and metadata, rather than an audio transcript or frame-by-frame motion analysis. `.DS_Store` is a system file and is excluded from project content.

![Preview of 12 silent video sequences](../Group-Project/CS5185_Project_Video_Dataset/preview.jpg)

The preview title is “CS5185 | 12 Silent Video Test Sequences,” arranged 01–12. Scene descriptions below are based only on that image; they do not establish motion intensity or experimental results.

| Video | Preview content | Split in brief |
| --- | --- | --- |
| [01_FourPeople.mp4](../Group-Project/CS5185_Project_Video_Dataset/01_FourPeople.mp4) | Four people seated around a table. | Development |
| [02_Beauty.mp4](../Group-Project/CS5185_Project_Video_Dataset/02_Beauty.mp4) | Portrait close-up with flowing hair. | Development |
| [03_Bosphorus.mp4](../Group-Project/CS5185_Project_Video_Dataset/03_Bosphorus.mp4) | Boat on water with a bridge and shore in the background. | Development |
| [04_HoneyBee.mp4](../Group-Project/CS5185_Project_Video_Dataset/04_HoneyBee.mp4) | Purple flowers. | Development |
| [05_Jockey.mp4](../Group-Project/CS5185_Project_Video_Dataset/05_Jockey.mp4) | Horse and jockey on a racecourse. | Final test |
| [06_ShakeNDry.mp4](../Group-Project/CS5185_Project_Video_Dataset/06_ShakeNDry.mp4) | Dog on a woodland path. | Final test |
| [07_Mobcal.mp4](../Group-Project/CS5185_Project_Video_Dataset/07_Mobcal.mp4) | Detailed ship photograph and patterned surroundings. | Development |
| [08_Shields.mp4](../Group-Project/CS5185_Project_Video_Dataset/08_Shields.mp4) | Person in front of a wall of heraldic shields. | Development |
| [09_Parkrun.mp4](../Group-Project/CS5185_Project_Video_Dataset/09_Parkrun.mp4) | Runner beside snow-covered ground and water. | Final test |
| [10_Stockholm.mp4](../Group-Project/CS5185_Project_Video_Dataset/10_Stockholm.mp4) | City buildings and waterfront. | Final test |
| [11_Sintel.mp4](../Group-Project/CS5185_Project_Video_Dataset/11_Sintel.mp4) | Animated character and flying creature. | Not assigned |
| [12_ControlledBurn.mp4](../Group-Project/CS5185_Project_Video_Dataset/12_ControlledBurn.mp4) | Burning building, smoke, trees, and a person nearby. | Not assigned |

### G2. Byte budgets and initial bitrate estimates

Shared JSON properties: 1280 × 720, 30 fps, no audio, H.264 lossless with libx264 QP 0. The stored `probe` data reports `h264`, High 4:4:4 Predictive profile, `yuv420p`, 8-bit samples, progressive scan, 16:9 display aspect, 1:1 sample aspect, and time base `1/15360`. ShakeNDry has 75 frames; all others have 150. Profile and pixel-format entries are retained as supplied.

These are newly calculated appendix-based budgets, separate from the printed brief table. Budget is `floor(bytes * ratio)`; initial video bitrate is `0.98 * 8 * target_bytes / duration / 1000`, shown in kbps to three decimals. These are estimates, not measured encoding results. Actual size and SHA-256 of all 12 local MP4 files were checked against JSON and matched. ffprobe and full playback were not rerun.

| Video | Duration s | Original bytes | 5% bytes | 5% initial kbps | 2% bytes | 2% initial kbps |
| --- | --- | --- | --- | --- | --- | --- |
| FourPeople | 5 | 63899977 | 3194998 | 5009.757 | 1277999 | 2003.902 |
| Beauty | 5 | 87093417 | 4354670 | 6828.123 | 1741868 | 2731.249 |
| Bosphorus | 5 | 64693675 | 3234683 | 5071.983 | 1293873 | 2028.793 |
| HoneyBee | 5 | 72578682 | 3628934 | 5690.169 | 1451573 | 2276.066 |
| Jockey | 5 | 71100729 | 3555036 | 5574.296 | 1422014 | 2229.718 |
| ShakeNDry | 2.5 | 41183285 | 2059164 | 6457.538 | 823665 | 2583.013 |
| Mobcal | 5 | 97252500 | 4862625 | 7624.596 | 1945050 | 3049.838 |
| Shields | 5 | 99405701 | 4970285 | 7793.407 | 1988114 | 3117.363 |
| Parkrun | 5 | 115970271 | 5798513 | 9092.068 | 2319405 | 3636.827 |
| Stockholm | 5 | 99309280 | 4965464 | 7785.848 | 1986185 | 3114.338 |
| Sintel | 5 | 16181723 | 809086 | 1268.647 | 323634 | 507.458 |
| ControlledBurn | 5 | 58156021 | 2907801 | 4559.432 | 1163120 | 1823.772 |

### G3. Sources and extraction offsets

`start_seconds` is the source extraction offset recorded in metadata. URLs are copied from local records without online refresh.

| Video | Source label | Start s | Original asset |
| --- | --- | --- | --- |
| FourPeople | Xiph | 1 | [FourPeople_1280x720_60.y4m](https://media.xiph.org/video/derf/y4m/FourPeople_1280x720_60.y4m) |
| Beauty | UVG | 0 | [Beauty_1920x1080_120fps_420_8bit_YUV_RAW.7z](https://ultravideo.fi/video/Beauty_1920x1080_120fps_420_8bit_YUV_RAW.7z) |
| Bosphorus | UVG | 0 | [Bosphorus_1920x1080_120fps_420_8bit_YUV_RAW.7z](https://ultravideo.fi/video/Bosphorus_1920x1080_120fps_420_8bit_YUV_RAW.7z) |
| HoneyBee | UVG | 0 | [HoneyBee_1920x1080_120fps_420_8bit_YUV_RAW.7z](https://ultravideo.fi/video/HoneyBee_1920x1080_120fps_420_8bit_YUV_RAW.7z) |
| Jockey | UVG | 0 | [Jockey_1920x1080_120fps_420_8bit_YUV_RAW.7z](https://ultravideo.fi/video/Jockey_1920x1080_120fps_420_8bit_YUV_RAW.7z) |
| ShakeNDry | UVG | 0 | [ShakeNDry_1920x1080_120fps_420_8bit_YUV_RAW.7z](https://ultravideo.fi/video/ShakeNDry_1920x1080_120fps_420_8bit_YUV_RAW.7z) |
| Mobcal | Xiph | 1 | [720p50_mobcal_ter.y4m](https://media.xiph.org/video/derf/y4m/720p50_mobcal_ter.y4m) |
| Shields | Xiph | 1 | [720p50_shields_ter.y4m](https://media.xiph.org/video/derf/y4m/720p50_shields_ter.y4m) |
| Parkrun | Xiph | 1 | [720p50_parkrun_ter.y4m](https://media.xiph.org/video/derf/y4m/720p50_parkrun_ter.y4m) |
| Stockholm | Xiph | 1 | [720p5994_stockholm_ter.y4m](https://media.xiph.org/video/derf/y4m/720p5994_stockholm_ter.y4m) |
| Sintel | Xiph | 28 | [sintel_trailer_2k_720p24.y4m](https://media.xiph.org/video/derf/y4m/sintel_trailer_2k_720p24.y4m) |
| ControlledBurn | Xiph | 7 | [controlled_burn_1080p.y4m](https://media.xiph.org/video/derf/y4m/controlled_burn_1080p.y4m) |

### G4. Complete original metadata records

All fields and values are retained below, including SHA-256, stream/container probe data, tags, disposition flags, original Windows paths, and encoder versions. JSON keys remain unchanged. `bytes` is file size; `duration` is duration; `fps` is frame rate; `audio` indicates audio presence; `sha256` is the checksum; `probe.streams` and `probe.format` describe streams and container.

<details>
<summary>01_FourPeople.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/01_FourPeople.json)

```json
{
  "name": "FourPeople",
  "url": "https://media.xiph.org/video/derf/y4m/FourPeople_1280x720_60.y4m",
  "file": "01_FourPeople.mp4",
  "source": "Xiph",
  "duration": 5,
  "start_seconds": 1,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 63899977,
  "sha256": "274dc6717af23204f7741727558cdf781d07f031aeaa0fa3cac597033d4b71c9",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "center",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "102237156",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 46,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\01_FourPeople.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "63899977",
      "bit_rate": "102239963",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>02_Beauty.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/02_Beauty.json)

```json
{
  "name": "Beauty",
  "url": "https://ultravideo.fi/video/Beauty_1920x1080_120fps_420_8bit_YUV_RAW.7z",
  "file": "02_Beauty.mp4",
  "source": "UVG",
  "duration": 5,
  "start_seconds": 0,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 87093417,
  "sha256": "54a4e24135ec8b3b82e94b2d7873a323f470b019ae7e8a57293602a2e65f1c0f",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "139346184",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\02_Beauty.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "87093417",
      "bit_rate": "139349467",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>03_Bosphorus.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/03_Bosphorus.json)

```json
{
  "name": "Bosphorus",
  "url": "https://ultravideo.fi/video/Bosphorus_1920x1080_120fps_420_8bit_YUV_RAW.7z",
  "file": "03_Bosphorus.mp4",
  "source": "UVG",
  "duration": 5,
  "start_seconds": 0,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 64693675,
  "sha256": "866e9f039f6840c413421c6071f3196aac021d519f9902aaad030a1eb34344ad",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "103507076",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\03_Bosphorus.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "64693675",
      "bit_rate": "103509880",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>04_HoneyBee.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/04_HoneyBee.json)

```json
{
  "name": "HoneyBee",
  "url": "https://ultravideo.fi/video/HoneyBee_1920x1080_120fps_420_8bit_YUV_RAW.7z",
  "file": "04_HoneyBee.mp4",
  "source": "UVG",
  "duration": 5,
  "start_seconds": 0,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 72578682,
  "sha256": "6002dbdccea6033de3294ac1bfa04d1305e81e7d6381bef87006517ad1c7f353",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "116123043",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\04_HoneyBee.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "72578682",
      "bit_rate": "116125891",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>05_Jockey.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/05_Jockey.json)

```json
{
  "name": "Jockey",
  "url": "https://ultravideo.fi/video/Jockey_1920x1080_120fps_420_8bit_YUV_RAW.7z",
  "file": "05_Jockey.mp4",
  "source": "UVG",
  "duration": 5,
  "start_seconds": 0,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 71100729,
  "sha256": "ea53c006e9361daa918aaee2a2113402c3c148fa44ead1ff1d62d92c9e1d1ca6",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "113758350",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\05_Jockey.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "71100729",
      "bit_rate": "113761166",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>06_ShakeNDry.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/06_ShakeNDry.json)

```json
{
  "name": "ShakeNDry",
  "url": "https://ultravideo.fi/video/ShakeNDry_1920x1080_120fps_420_8bit_YUV_RAW.7z",
  "file": "06_ShakeNDry.mp4",
  "source": "UVG",
  "duration": 2.5,
  "start_seconds": 0,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 41183285,
  "sha256": "1b105f318e5061e585a0235fa7f9600cb926fc576cf96fd3f9eaa2bc59f85512",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 38400,
        "duration": "2.500000",
        "bit_rate": "131781993",
        "bits_per_raw_sample": "8",
        "nb_frames": "75",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\06_ShakeNDry.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "2.500000",
      "size": "41183285",
      "bit_rate": "131786512",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>07_Mobcal.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/07_Mobcal.json)

```json
{
  "name": "Mobcal",
  "url": "https://media.xiph.org/video/derf/y4m/720p50_mobcal_ter.y4m",
  "file": "07_Mobcal.mp4",
  "source": "Xiph",
  "duration": 5,
  "start_seconds": 1,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 97252500,
  "sha256": "b6899426199fa7f7dfe23e4fa20cc00bd34b0849aa1c22cd5c24cd423aa1b96d",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "155600716",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\07_Mobcal.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "97252500",
      "bit_rate": "155604000",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>08_Shields.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/08_Shields.json)

```json
{
  "name": "Shields",
  "url": "https://media.xiph.org/video/derf/y4m/720p50_shields_ter.y4m",
  "file": "08_Shields.mp4",
  "source": "Xiph",
  "duration": 5,
  "start_seconds": 1,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 99405701,
  "sha256": "7356726c9e92a945d522f1def0278588d3746f19904c17a7d977be3f1d4eb0a7",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "159045838",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\08_Shields.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "99405701",
      "bit_rate": "159049121",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>09_Parkrun.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/09_Parkrun.json)

```json
{
  "name": "Parkrun",
  "url": "https://media.xiph.org/video/derf/y4m/720p50_parkrun_ter.y4m",
  "file": "09_Parkrun.mp4",
  "source": "Xiph",
  "duration": 5,
  "start_seconds": 1,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 115970271,
  "sha256": "2ddef466641098d4d20e7d67a890ac2842ab92bbe2b8df3de1266210d4b6b921",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "185549150",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\09_Parkrun.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "115970271",
      "bit_rate": "185552433",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>10_Stockholm.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/10_Stockholm.json)

```json
{
  "name": "Stockholm",
  "url": "https://media.xiph.org/video/derf/y4m/720p5994_stockholm_ter.y4m",
  "file": "10_Stockholm.mp4",
  "source": "Xiph",
  "duration": 5,
  "start_seconds": 1,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 99309280,
  "sha256": "706bd0e317ab0db0a54bfab1cf24f683c8eb7e1acb8b4e40e0e4f1f630f29fe0",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "158891564",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\10_Stockholm.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "99309280",
      "bit_rate": "158894848",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>11_Sintel.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/11_Sintel.json)

```json
{
  "name": "Sintel",
  "file": "11_Sintel.mp4",
  "source": "Xiph",
  "url": "https://media.xiph.org/video/derf/y4m/sintel_trailer_2k_720p24.y4m",
  "duration": 5,
  "start_seconds": 28,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 16181723,
  "sha256": "c6a983f1144fc0a49b89df8a109ff02245f1fc58450b56412a590c71a1b1177e",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "center",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "25888084",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 46,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\11_Sintel.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "16181723",
      "bit_rate": "25890756",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

<details>
<summary>12_ControlledBurn.json</summary>

[Source file](../Group-Project/CS5185_Project_Video_Dataset/metadata/12_ControlledBurn.json)

```json
{
  "name": "ControlledBurn",
  "file": "12_ControlledBurn.mp4",
  "source": "Xiph",
  "url": "https://media.xiph.org/video/derf/y4m/controlled_burn_1080p.y4m",
  "duration": 5,
  "start_seconds": 7,
  "width": 1280,
  "height": 720,
  "fps": 30,
  "audio": false,
  "encoding": "H.264 lossless, libx264 QP 0",
  "bytes": 58156021,
  "sha256": "87604fd72523b625c06b0dee60b6314e05e5f57825f7db841a840b0f286985d5",
  "probe": {
    "streams": [
      {
        "index": 0,
        "codec_name": "h264",
        "codec_long_name": "H.264 / AVC / MPEG-4 AVC / MPEG-4 part 10",
        "profile": "High 4:4:4 Predictive",
        "codec_type": "video",
        "codec_tag_string": "avc1",
        "codec_tag": "0x31637661",
        "width": 1280,
        "height": 720,
        "coded_width": 1280,
        "coded_height": 720,
        "closed_captions": 0,
        "film_grain": 0,
        "has_b_frames": 0,
        "sample_aspect_ratio": "1:1",
        "display_aspect_ratio": "16:9",
        "pix_fmt": "yuv420p",
        "level": 31,
        "chroma_location": "left",
        "field_order": "progressive",
        "refs": 1,
        "is_avc": "true",
        "nal_length_size": "4",
        "id": "0x1",
        "r_frame_rate": "30/1",
        "avg_frame_rate": "30/1",
        "time_base": "1/15360",
        "start_pts": 0,
        "start_time": "0.000000",
        "duration_ts": 76800,
        "duration": "5.000000",
        "bit_rate": "93046753",
        "bits_per_raw_sample": "8",
        "nb_frames": "150",
        "extradata_size": 44,
        "disposition": {
          "default": 1,
          "dub": 0,
          "original": 0,
          "comment": 0,
          "lyrics": 0,
          "karaoke": 0,
          "forced": 0,
          "hearing_impaired": 0,
          "visual_impaired": 0,
          "clean_effects": 0,
          "attached_pic": 0,
          "timed_thumbnails": 0,
          "non_diegetic": 0,
          "captions": 0,
          "descriptions": 0,
          "metadata": 0,
          "dependent": 0,
          "still_image": 0,
          "multilayer": 0
        },
        "tags": {
          "language": "und",
          "handler_name": "VideoHandler",
          "vendor_id": "[0][0][0][0]",
          "encoder": "Lavc61.19.101 libx264"
        }
      }
    ],
    "format": {
      "filename": "CS5185_Project_Video_Dataset\\12_ControlledBurn.mp4",
      "nb_streams": 1,
      "nb_programs": 0,
      "nb_stream_groups": 0,
      "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
      "format_long_name": "QuickTime / MOV",
      "start_time": "0.000000",
      "duration": "5.000000",
      "size": "58156021",
      "bit_rate": "93049633",
      "probe_score": 100,
      "tags": {
        "major_brand": "isom",
        "minor_version": "512",
        "compatible_brands": "isomiso2avc1mp41",
        "encoder": "Lavf61.7.100"
      }
    }
  }
}
```

</details>

## H. License and source text extraction

The local files provide the following provenance and usage statements. These describe the supplied records, without a current online/legal review.

| Files / sequences | Local statement |
| --- | --- |
| Beauty, Bosphorus, HoneyBee, Jockey, ShakeNDry copyright files | Sequence and intellectual-property rights remain with Digiturk; use under CC BY-NC 3.0 Unported. |
| FourPeople_source.txt | Publisher labels it public domain. Access recorded 2026-10-25; teaching derivative uses seconds 1–6 at 720p/30 fps, silent, H.264 lossless. |
| Sintel_attribution.txt | Blender Foundation, CC BY 3.0; five-second silent 720p derivative, frame repetition from 24 to 30 fps, H.264 lossless. |
| NTIA_HDTV_Readme.txt | NTIA/ITS ownership, research only; acceptance of terms and preservation of the notice/acknowledgment required for copied or derived works. Includes upstream camera and scene details for ControlledBurn and other sequences. |
| SVT_720p_ReadMe.txt | Historical sequence, camera, sampling, producer and contact details; local README says “No restrictions” and “No copyright.” |

### H1. Complete original texts

All nine files are reproduced below, including upstream technical details and usage conditions. Line endings are normalized to LF. Upstream durations, resolutions, and frame counts describe source assets, not the local five-second/2.5-second teaching derivatives. The SVT notice's statement that one source variant was temporarily removed is historical text, not a claim that a local video is missing.

#### Beauty_Copyright.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/Beauty_Copyright.txt)

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### Bosphorus_Copyright.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/Bosphorus_Copyright.txt)

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### FourPeople_source.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/FourPeople_source.txt)

```text
FourPeople
Source: https://media.xiph.org/video/derf/
The publisher labels FourPeople as public domain.
Download: https://media.xiph.org/video/derf/y4m/FourPeople_1280x720_60.y4m
Accessed: 2026-10-25
Teaching derivative: seconds 1-6, 720p, 30 fps, silent, H.264 lossless.
```

#### HoneyBee_Copyright.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/HoneyBee_Copyright.txt)

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### Jockey_Copyright.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/Jockey_Copyright.txt)

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### NTIA_HDTV_Readme.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/NTIA_HDTV_Readme.txt)

```text
These video sequences are owned by NTIA/ITS, an agency of the U.S. Federal
Government.  They were created under Project Number 3141012-300, Video Quality
Research, in 2008.  These video sequences may be used for research purposes,
only.  You can use, copy, modify and redistribute them upon your acceptance of
these terms and conditions and upon your express agreement to provide
appropriate acknowledgments of NTIA/ITS's ownership of the video sequences by
keeping this text present with any copied or derived works.

Video Standard: 1080p 30fps
Camera specs:   Panasonic AJ-HDX-900, saved to DVCPro tape.
Video standard: Native
Editing:        19 second clips, intended to remove first 2-sec and final 2-sec.
Scenes:
      Aspen
      RedKayak
      WestWindEasy



Video Standard: 1080p 30fps
Camera specs:   The camera was a Panasonic P2HD AJ-HPX3000G; and the lens a
                Fujinon TV Lens HA22x7.8 BERM-M48. This camera records in H.264
                intra-frame coding at 100 Mbps.
Video standard: Native
Editing:        19 second clips, intended to remove first 2-sec and final 2-sec.
Scenes:
      RushFieldCuts -- shutter speed 30
      SnowMnt -- shutter speed 30
      SpeedBag -- shutter speed 60
      TouchdownPass -- shutter speed 30




Video Standard: 1080p 30fps
Camera specs:   The camera was a Sony HVR-Z1U (HDV format) which was
                converted to SMPTE 292M (high definition 1080i format) and
                recorded onto a Panasonic HD-D5.
Use restrictions: research purposes, only
Notes:          Video of fire was taken of a controlled burn of a Meth house.
Video standard: Native
Editing:        19 second clips, intended to remove first 2-sec and final 2-sec.
Scenes:
      ControlledBurn
```

#### SVT_720p_ReadMe.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/SVT_720p_ReadMe.txt)

```text
Sequence		#Frames	Short description
--------------------------------------------------
720p50_mobcal_ter	504 (incl. 4 mid grey frames)	Similar to Mobile&Calendar. Close up. Moving calendar with text and a detailed photo of the Vasa ship. Moving train with colorful toys. Background with two types of wallpaper, one brown with details and one yellow with drawn figures. Very detailed and normally demanding.
720p50_parkrun_ter	504 (incl. 4 mid grey frames)	Long shot. Man running in a park with an umbrella in his hand. Trees, snow and water in the background. Very detailed and demanding.
temporarely removed due to wrong pixels: 720p50_stockholm_ter	504 (incl. 2 mid grey frames)	Panning view over the Old Town of Stockholm. Detailed houses, water and moving cars.Panning view over the Old Town of Stockholm. Detailed houses, water and moving cars.
720p50_shields_ter	504 (incl. 2 mid grey frames)	Man with beard and a speckled jacket walking in front of a wall of detailed knight shields. Zoom at the end of the sequence.

720p5994_parkrun_ter	604 (incl. 4 mid grey frames)	Long shot. Man running in a park with an umbrella in his hand. Trees, snow and water in the background. Very detailed and demanding.
720p5994_stockholm_ter	604 (incl. 2 mid grey frames)	Panning view over the Old Town of Stockholm. Detailed houses, water and moving cars.Panning view over the Old Town of Stockholm. Detailed houses, water and moving cars.
720p5994_shields_ter	604 (incl. 2 mid grey frames)	Man with beard and a speckled jacket walking in front of a wall of detailed knight shields. Zoom at the end of the sequence.


Camera: Thomson LDK6000
Lenses: Canon HJ9X5.5KLL-SC zoom-lense
Recorded on: Native 10 bit 4:2:2 on DVS HDStationPlus
Stored on: DVS HDStationPlus Diskrecorder
Frame rate: 50 fps (progressive)
Resolution: 1280x720
Color subsampling: 4:2:0
Filter Tabs for Subsampling	-0.0063 / 0 / 0.0299 / 0 / -0.0831 / 0 / 0.3098  / 0.4994 / 0.3098 / 0 / -0.0831 / 0 / 0.0299 / 0 / -0.0063
Color conversion: SMPTE 296M
Original files contact: Lars.Haglund@svt.se -
        see also http://www.svt.se/svtinfo/inenglish/dev/  and download
        http://www.svt.se/svtinfo/inenglish/dev/svt_widexga_final.pdf
Restrictions of use:	No restrictions
Copyright:	No copyright
Producer:	SVT Sveriges Television AB, Lars Haglund
Camera Operator:	Jan-Hugo Norman & Team

All material was recorded in december 2001 by SVT Sveriges Television AB.
```

#### ShakeNDry_Copyright.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/ShakeNDry_Copyright.txt)

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### Sintel_attribution.txt

[Source file](../Group-Project/CS5185_Project_Video_Dataset/licenses/Sintel_attribution.txt)

```text
Sintel trailer excerpt
Copyright Blender Foundation | https://durian.blender.org
Creative Commons Attribution 3.0: https://creativecommons.org/licenses/by/3.0/
Publisher license and attribution: https://durian.blender.org/sharing/
Source: https://media.xiph.org/video/derf/y4m/sintel_trailer_2k_720p24.y4m
Teaching derivative: 5-second silent excerpt, 720p, frame repetition from 24 to 30 fps, H.264 lossless.
```

