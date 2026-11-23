# CS5185 Content-Adaptive Video Encoding System

Language: English. [中文](Project_Description_ZH.md) · [Implementation and dataset appendix](Implementation_and_Dataset_EN.md)

- Group size: 3–4 students.
- Project duration: 4 weeks.
- Final presentation: Week 13, 5 minutes per group.

## 1. Background and motivation

Video encoding aims to maintain video transmission quality while reducing the bitrate required for transmission. Different videos vary in their degree of visual change. Slides, presentations, and fixed-camera scenes often contain large regions that change very little. Other videos contain people walking, camera movement, or scene cuts. Sports, competitions, and fast-moving shots exhibit large differences between consecutive frames. Therefore, no single set of encoder parameters is optimal for all videos; different content types need different encoding configurations.

This project aims to build a content-adaptive video encoding system that selects encoding parameters according to video content. One possible design checks the compressed file size and reconstructed quality, adjusts parameters, and re-encodes when necessary. The goal is to maximize encoded video quality at a given compression ratio.

For example, a fixed-camera cityscape changes little but still needs sharp building edges. A soccer match contains fast player movement and changes across multiple regions between frames. The same settings may therefore produce different compression results.

## 2. Task requirements

Build a runnable content-adaptive video encoding system. Compress the 12 provided silent `.mp4` videos to two target file sizes: **5% and 2% of each original file size**.

The system may analyze the original content, calculate target video bitrate from target file size and duration, automatically determine x264 parameters, invoke FFmpeg to generate the compressed bitstream, inspect actual size and quality, and adjust parameters when necessary. The complete loop comprises content analysis, parameter decision, FFmpeg encoding, result inspection, and feedback adjustment.

Each group may choose rules, formulas, weighted scoring, candidate parameter search, deep learning, an LLM, a multimodal LLM, or a combination. The choice must be justified.

The final deliverables include a playable, full-duration video decoded from the compressed bitstream and a report documenting the system design, final encoding strategy, and subjective comparison of decoded outputs.

The project involves **parameter selection for x264**, with no x264 source-code modification. All encoding and muxing must use FFmpeg. LLMs may assist with coding and writing.

## 3. Detailed requirements

### 3.1. Videos and development/test split

The `CS5185_Project_Video_Dataset` folder contains 12 videos. Each is 5 seconds long except ShakeNDry, which is 2.5 seconds. All have resolution 1280 × 720, frame rate 30 fps, and no audio. The `metadata` directory provides resolution, frame rate, original size, and other information for calculating budgets.

Calculate target budgets from original byte counts using decimal MB. Initial video bitrate reserves a 2% margin for container overhead; actual output size must still be checked after encoding. See the [implementation and dataset appendix](Implementation_and_Dataset_EN.md) for the calculation method.

| Input video | Duration (s) | Original size (MB) | 5% byte budget | 5% initial bitrate (kbps) | 2% byte budget | 2% initial bitrate (kbps) |
| --- | --- | --- | --- | --- | --- | --- |
| `01_FourPeople.mp4` | 5 | 63.899977 | 3194998 | 5009.757 | 1277999 | 2003.902 |
| `02_Beauty.mp4` | 5 | 87.093417 | 4354670 | 6828.123 | 1741868 | 2731.249 |
| `03_Bosphorus.mp4` | 5 | 64.693675 | 3234683 | 5071.983 | 1293873 | 2028.793 |
| `04_HoneyBee.mp4` | 5 | 72.578682 | 3628934 | 5690.169 | 1451573 | 2276.066 |
| `05_Jockey.mp4` | 5 | 71.100729 | 3555036 | 5574.296 | 1422014 | 2229.718 |
| `06_ShakeNDry.mp4` | 2.5 | 41.183285 | 2059164 | 6457.538 | 823665 | 2583.013 |
| `07_Mobcal.mp4` | 5 | 97.252500 | 4862625 | 7624.596 | 1945050 | 3049.838 |
| `08_Shields.mp4` | 5 | 99.405701 | 4970285 | 7793.407 | 1988114 | 3117.363 |
| `09_Parkrun.mp4` | 5 | 115.970271 | 5798513 | 9092.068 | 2319405 | 3636.827 |
| `10_Stockholm.mp4` | 5 | 99.309280 | 4965464 | 7785.848 | 1986185 | 3114.338 |
| `11_Sintel.mp4` | 5 | 16.181723 | 809086 | 1268.647 | 323634 | 507.458 |
| `12_ControlledBurn.mp4` | 5 | 58.156021 | 2907801 | 4559.432 | 1163120 | 1823.772 |

Use videos **01, 02, 03, 04, 07, 08** for development. Reserve **05, 06, 09, 10** for final testing. Run the test videos through the adaptive system, then compare decoded outputs subjectively against the provided originals. Videos 11–12 have no designated development/test split; all 12 videos must be compressed at both target ratios.

### 3.2. Content feature analysis

Each group may select its own content-analysis method. Examples include frame-to-frame differences, motion intensity, edge or texture complexity, scene changes, and local brightness variation. Pretrained neural networks or vision large language models (VLLMs) may extract features. Analysis can cover an entire video, segments, or time windows.

Explain the method and how its results support subsequent parameter selection. The number, type, and computation of features are unrestricted; the analysis must actually inform encoding decisions.

### 3.3. Parameter decision

Combine the target size and content-analysis results to generate an encoding plan, then invoke FFmpeg x264. Parameters may include preset, CRF/CBR/CQP mode, target bitrate, quantization parameter, keyframe interval, and other settings.

Groups decide how to map content to settings, for example adjusting bitrate according to motion or using an LLM as a judge to output FFmpeg parameters. Explain the parameters, adjustment rules, and use of formulas, search, or models. Present the corresponding encoding settings and compression results. There is no prescribed decision method; the connection between content and decisions must be clear and reasonable.

### 3.4. FFmpeg encoding and feedback adjustment

All encoding and muxing must use FFmpeg. Check the actual compressed bitstream size. If it exceeds the target, adjust parameters according to the design rules and re-encode. A maximum of **2–3 adjustment rounds** is recommended, saving the parameters, actual bitstream size, and reason for each adjustment.

Once final bitrate has converged to the target, use FFmpeg to decode the binary bitstream and restore `.mp4` output. Output must be playable and full-duration. **Do not meet size limits by shortening the video or removing content.**

### 3.5. Result analysis

Use course-provided originals as reference videos. Present at least three videos, with original references, a unified baseline, and adaptive results. Test both size targets for each video and report:

- Target and actual file size.
- Target and actual bitrate.
- Main FFmpeg parameters and runtime.
- Representative frames or short clips at matching temporal positions.
- A content-feature timeline or curve, with one segment explaining what was detected, which parameters were used, and why.

Evaluate target-size compliance, full playback, motion smoothness, and visible blur, blocking, ghosting, or detail loss. Use both **PSNR and MS-SSIM**, together with local frame inspection.

### 3.6. Permitted tools

All encoding and muxing must use FFmpeg. FFprobe, Python, OpenCV, NumPy, and existing libraries may read metadata, compute features, evaluate quality, and generate logs. No other video encoder may replace FFmpeg. A command-line interface or simple desktop app is sufficient. Web deployment and real-time processing are not required. LLMs may assist with coding and writing.

## 4. Grading rubric

Assessment emphasizes system completeness, clear experimental analysis, and an understandable, reproducible report. Final numerical performance accounts for 10%; absolute result quality is not the main grading basis. The system should run as designed and the explanations should have sufficient evidence.

| Grading item | Weight | Main criteria |
| --- | --- | --- |
| System functional completeness | 35% | Complete content analysis, parameter decision, FFmpeg encoding, inspection, and feedback; stable execution. |
| Experimental design and analysis | 25% | Different content types, fair baseline, analysis of features/parameters/results, and explained cases. |
| Report clarity and reproducibility | 20% | Clear task, methods, workflow, parameters, setup, results, and limitations; reproducible code and steps. |
| Presentation and team collaboration | 10% | Clear demonstration of the full workflow and clear report explanation. |
| Result performance | 10% | File-size control, PSNR, MS-SSIM, and subjective quality. |

## 5. Submission and presentation

1. **Runnable code:** dependencies, launch commands, FFmpeg version and invocation method, and input constraints; reproduce the complete input-to-output pipeline.
2. **Project report:** workflow, feature algorithms, parameter decision, feedback adjustment, experiments, limitations, member contributions, and third-party image/tool sources.
3. **Experimental results:** parameters/results for at least three decoded videos; representative screenshots or clips; analyzable decision evidence such as feature curves, adjustment logs, and dataset video identifiers.
4. **Presentation materials:** approximately 5–6 slides explaining workflow, results, and a brief analysis.

Each group gives a **5-minute final presentation**. Focus on how one video's content triggers particular decisions and what observable changes follow. Evaluation considers completeness, connection to course knowledge, experimental fairness, and explanatory clarity. The presentation takes place in **Week 13** and should compare baseline/adaptive results and discuss limitations.

## 6. Four-week schedule

| Time | Main tasks |
| --- | --- |
| Week 1 | Understand content variation versus encoding effects; choose features and rules; prepare data; run the unified FFmpeg baseline. |
| Week 2 | Implement metadata reading, feature analysis, timeline visualization, and preliminary parameter decision. |
| Week 3 | Complete encoding, over-target adjustment, and tests on three content types; analyze successes and failures. |
| Week 4 | Fix issues; organize code, logs, and results; finish report, slides, and presentation rehearsal. |

## 7. Group formation and communication

### 7.1. Canvas groups

Canvas provides 50 pre-created groups, with up to four students per group. Students may join a group or create their own and invite classmates.

Use **People > Groups** to find or join a group. Select **+ Group** to create one, enter Group Name, configure Joining, and use Invite Students to add classmates. Groups provide a calendar, wiki, discussions, file space, document collaboration, and web-conference scheduling.

### 7.2. Project questions

Post project questions in **Canvas Discussions**. The teaching team will reply when they see them. Detailed requirements and implementation guidelines are published through Canvas.
