# CS5185 Content-Adaptive Video Encoding System

Language: English. [中文](Project_Description_ZH.md) · [Implementation and dataset appendix](Implementation_and_Dataset_EN.md)

Sources: [CS5185_Project_Description.pdf](../Group-Project/CS5185_Project_Description.pdf), pp. 1–6, and [Project_Introduction.pptx](../Group-Project/Project_Introduction.pptx), 15 slides. The requirements below follow the PDF; slide-specific additions are identified separately. Source inconsistencies are preserved and annotated in Section 8.

- Group size: 3–4 students.
- Project duration: 4 weeks.
- Final presentation: 5 minutes per group; the slides specify Week 13.

## 1. Background and motivation

Video encoding aims to maintain video transmission quality while reducing the bitrate required for transmission. Different videos vary in their degree of visual change. Slides, presentations, and fixed-camera scenes often contain large regions that change very little. Other videos contain people walking, camera movement, or scene cuts. Sports, competitions, and fast-moving shots exhibit large differences between consecutive frames. Therefore, no single set of encoder parameters is optimal for all videos; different content types need different encoding configurations.

This project aims to build a content-adaptive video encoding system that selects encoding parameters according to video content. One possible design checks the compressed file size and reconstructed quality, adjusts parameters, and re-encodes when necessary. The goal is to maximize encoded video quality at a given compression ratio.

**Figure 1, rendered as text:** Low-motion cityscape: with a fixed camera, most regions change little, but building edges still need to remain sharp. High-motion soccer match: players move quickly, and multiple regions change between consecutive frames. Different content exhibits different degrees of visual change, so the same parameter settings may produce different compression results. The original images remain on PDF p. 1 and PPT slide 1.

## 2. Task requirements

Build a runnable content-adaptive video encoding system. Compress the 12 provided silent `.mp4` videos to two target file sizes: **5% and 2% of each original file size**.

The system may analyze the original content, calculate target video bitrate from target file size and duration, automatically determine x264 parameters, invoke FFmpeg to generate the compressed bitstream, inspect actual size and quality, and adjust parameters when necessary. The complete loop comprises content analysis, parameter decision, FFmpeg encoding, result inspection, and feedback adjustment.

Each group may choose rules, formulas, weighted scoring, candidate parameter search, deep learning, an LLM, a multimodal LLM, or a combination. The choice must be justified.

The final deliverables include a playable, full-duration video decoded from the compressed bitstream and a report documenting the system design, final encoding strategy, and subjective comparison of decoded outputs.

The project involves **parameter selection for x264**, with no x264 source-code modification. All encoding and muxing must use FFmpeg. LLMs may assist with coding and writing.

## 3. Detailed requirements

### 3.1. Videos and development/test split

The [dataset folder](../Group-Project/CS5185_Project_Video_Dataset) contains 12 videos. Each is 5 seconds long except ShakeNDry, which is 2.5 seconds. All have resolution 1280 × 720, frame rate 30 fps, and no audio. The `metadata` directory provides resolution, frame rate, original size, and other information for calculating budgets.

The following table preserves the **PDF's rounded values**, including its inconsistent entries. Use the byte-based method in the appendix for implementation.

| Input video | Original size (MB) | 5% target size and bitrate | 2% target size and bitrate |
| --- | --- | --- | --- |
| 01_FourPeople.mp4 (5s) | 63.90 | 3 MB; 4.8 Mbps | 1.2 MB; 1.9 Mbps |
| 02_Beauty.mp4 (5s) | 87.09 | 4 MB; 6.4 Mbps | 1.7 MB; 2.7 Mbps |
| 03_Bosphorus.mp4 (5s) | 64.69 | 3 MB; 4.8 Mbps | 1.3 MB; 2.1 Mbps |
| 04_HoneyBee.mp4 (5s) | 72.58 | 4 MB; 6.4 Mbps | 1.4 MB; 2.2 Mbps |
| 05_Jockey.mp4 (5s) | 71.10 | 4 MB; 6.4 Mbps | 1.4 MB; 2.2 Mbps |
| 06_ShakeNDry.mp4 (2.5s) | 41.18 | 2 MB; 6.4 Mbps | 0.8 MB; 1.3 Mbps |
| 07_Mobcal.mp4 (5s) | 97.25 | 5 MB; 8.0 Mbps | 1.9 MB; 3.4 Mbps |
| 08_Shields.mp4 (5s) | 99.41 | 5 MB; 8.0 Mbps | 2.0 MB; 3.2 Mbps |
| 09_Parkrun.mp4 (5s) | 115.97 | 6 MB; 9.6 Mbps | 2.3 MB; 3.7 Mbps |
| 10_Stockholm.mp4 (5s) | 99.31 | 5 MB; 8.0 Mbps | 2.0 MB; 3.2 Mbps |
| 11_Sintel.mp4 (5s) | 16.18 | 1 MB; 1.6 Mbps | 0.3 MB; 0.5 Mbps |
| 12_ControlledBurn.mp4 (5s) | 58.16 | 3 MB; 4.8 Mbps | 1.1 MB; 18 Mbps |

Use videos **01, 02, 03, 04, 07, 08** for development. Reserve **05, 06, 09, 10** for final testing. Run the test videos through the adaptive system, then compare decoded outputs subjectively against the provided originals. The brief does not assign videos 11–12 to either split, although the overall task covers all 12.

### 3.2. Content feature analysis

Each group may select its own content-analysis method. Examples include frame-to-frame differences, motion intensity, edge or texture complexity, scene changes, and local brightness variation. Pretrained neural networks or vision large language models (VLLMs) may extract features. Analysis can cover an entire video, segments, or time windows.

Explain the method and how its results support subsequent parameter selection. The number, type, and computation of features are unrestricted; the analysis must actually inform encoding decisions.

### 3.3. Parameter decision

Combine the target size and content-analysis results to generate an encoding plan, then invoke FFmpeg x264. Parameters may include preset, CRF/CBR/CQP mode, target bitrate, quantization parameter, keyframe interval, and other settings.

Groups decide how to map content to settings, for example adjusting bitrate according to motion or using an LLM as a judge to output FFmpeg parameters. Explain the parameters, adjustment rules, and use of formulas, search, or models. Present the corresponding encoding settings and compression results. There is no prescribed decision method; the connection between content and decisions must be clear and reasonable.

### 3.4. FFmpeg encoding and feedback adjustment

All encoding and muxing must use FFmpeg. Check the actual compressed bitstream size. If it exceeds the target, adjust parameters according to the design rules and re-encode. The brief recommends at most **2–3 adjustment rounds**, saving the parameters, actual bitstream size, and reason for each adjustment.

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

The PDF labels this section “3.5 Permitted Tools,” repeating the previous number; it is renumbered here for navigation.

All encoding and muxing must use FFmpeg. FFprobe, Python, OpenCV, NumPy, and existing libraries may read metadata, compute features, evaluate quality, and generate logs. No other video encoder may replace FFmpeg. A command-line interface or simple desktop app is sufficient. Web deployment and real-time processing are not required. LLMs may assist with coding and writing.

## 4. Grading rubric

Assessment emphasizes system completeness, clear experimental analysis, and an understandable, reproducible report. Final numerical performance accounts for 10%; absolute result quality is not the main grading basis. The system should run as designed and the explanations should have sufficient evidence.

| Grading item in PDF | Weight | Main criteria |
| --- | --- | --- |
| System functional completeness | 35% | Complete content analysis, parameter decision, FFmpeg encoding, inspection, and feedback; stable execution. |
| Experimental design and analysis | 25% | Different content types, fair baseline, analysis of features/parameters/results, and explained cases. |
| Report clarity and reproducibility | 20% | Clear task, methods, workflow, parameters, setup, results, and limitations; reproducible code and steps. |
| Presentation and team collaboration | 10% | Clear demonstration of the full workflow and clear report explanation. |
| Presentation and team collaboration [repeated source label] | 10% | Final size control, PSNR, MS-SSIM, and subjective quality. PPT slide 13 calls this “Result performance.” |

## 5. Submission and presentation

1. **Runnable code:** dependencies, launch commands, FFmpeg version and invocation method, and input constraints; reproduce the complete input-to-output pipeline. The PDF spells FFmpeg as “Fmpeg” in this item.
2. **Project report:** workflow, feature algorithms, parameter decision, feedback adjustment, experiments, limitations, member contributions, and third-party image/tool sources.
3. **Experimental results:** parameters/results for at least three decoded videos; representative screenshots or clips; analyzable decision evidence such as feature curves, adjustment logs, and dataset video identifiers.
4. **Presentation materials:** approximately 5–6 slides explaining workflow, results, and a brief analysis.

Each group gives a **5-minute final presentation**. Focus on how one video's content triggers particular decisions and what observable changes follow. Evaluation considers completeness, connection to course knowledge, experimental fairness, and explanatory clarity. PPT slide 14 also asks for baseline/adaptive comparisons and limitations; slides 2 and 14 place the presentation in **Week 13**.

## 6. Four-week schedule

| Time | Main tasks |
| --- | --- |
| Week 1 | Understand content variation versus encoding effects; choose features and rules; prepare data; run the unified FFmpeg baseline. |
| Week 2 | Implement metadata reading, feature analysis, timeline visualization, and preliminary parameter decision. |
| Week 3 | Complete encoding, over-target adjustment, and tests on three content types; analyze successes and failures. |
| Week 4 | Fix issues; organize code, logs, and results; finish report, slides, and presentation rehearsal. |

## 7. PPT additions and slide index

### 7.1. Canvas group formation and questions

Slides 3–5 and 15 state that 50 empty groups have been pre-created in Canvas. Students may join any group, with up to four students per group, or create their own group and invite classmates. The screenshot shows **People > Groups**, a group search box, and **+ Group**. The “New Student Group” dialog contains Group Name, Joining (shown as “Course members are free to join”), Invite Students, Cancel, and Submit. Its explanatory text says groups have a calendar, wiki, discussions, file space, document collaboration, and web-conference scheduling.

Post project questions in **Canvas Discussions**; the teaching team will reply when they see them. Detailed requirements and implementation guidelines will be posted on Canvas. These are statements in the supplied slides, not a live check of Canvas.

### 7.2. Physical slide index

Physical slide positions are used because displayed slide numbers are irregular.

| Slide | Extracted topic | Destination |
| --- | --- | --- |
| 1 | Motivation; low and high motion; quality within a fixed size budget | Sections 1–2 |
| 2 | Runnable system; 12 videos; 5%/2%; complete playback; 3–4 students; four weeks; Week 13 presentation; LLM assistance | Sections 2 and 5 |
| 3 | 50 pre-created Canvas groups; maximum four members | Section 7.1 |
| 4 | Create a group and invite classmates | Section 7.1 |
| 5 | Canvas Discussions and future posting of detailed guidance | Section 7.1 |
| 6 | Input format, feature signals, models, timelines, decision linkage | Section 3 |
| 7 | Five-step system workflow | Sections 2–3 and appendix A |
| 8 | Three videos, both budgets, baseline, metrics, aligned evidence | Section 3.5 |
| 9 | DeepSeek provider configuration example | Appendix D |
| 10 | Registration/login screenshot | Appendix D |
| 11 | API key page screenshot | Appendix D |
| 12 | Image-only Chat API code example | Appendix D; transcribed from the image |
| 13 | Rubric; numerical results worth 10% | Section 4 |
| 14 | Deliverables, Week 13, five minutes, 5–6 slides | Section 5 |
| 15 | Canvas question/posting reminder | Section 7.1 |

Speaker notes on slides 1, 2, 7, 8, and 14 cite the supplied brief and appendix. Slide 6 notes the unassigned videos and conflicting rounded table. Slide 13 explains its renamed final rubric row. Notes for slides 9–11 date the DeepSeek documentation/screenshot checks to **27 October 2026**; see the appendix for those historical examples.

## 8. Source inconsistencies and extraction notes

- The PDF's table rounds budgets to whole or fractional MB; the implementation appendix explicitly requires `floor(S * r)` bytes without rounding budgets to whole MB.
- ShakeNDry's 2% row says 0.8 MB and 1.3 Mbps, inconsistent with its 2.5-second duration. ControlledBurn's 2% row says 1.1 MB and 18 Mbps. Mobcal's 1.9 MB and 3.4 Mbps also do not match each other for five seconds. Values above are retained as printed; the appendix provides separately calculated byte budgets and initial bitrate estimates.
- Videos 11–12 have no development/test assignment in the brief. The overall requirement remains 12 videos.
- The PDF repeats section 3.5 and the last rubric label. PPT slide 13 explicitly renames the last rubric row while retaining weights.
- The brief recommends 2–3 adjustment rounds; the optional appendix suggests three attempts in total, with two-pass encoding counting as one attempt. These are different counting conventions.
- Paragraphs and tables were reconstructed from the supplied documents. The images are described in text and remain available in the linked originals. API examples are documentary extraction, not verification of current provider behavior.
