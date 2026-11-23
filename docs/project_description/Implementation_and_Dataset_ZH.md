# CS5185 实现与数据集附录

语言：中文。[English](Implementation_and_Dataset_EN.md) · [项目说明](Project_Description_ZH.md)

本文提供编码系统的可选实现建议，包括大小控制、参数选择、模型接口、质量测量和数据集信息。具体实现方式由各组自行选择。

## 一、建议流程与大小控制

### A 建议流程

建议按以下顺序组织系统流程。

1. 读取元数据，确定大小预算。
2. 提取内容特征。
3. 选择并验证编码设置。
4. 编码原始输入。
5. 测量大小、解码情况、质量和耗时。
6. 判断重试是否有价值，以及是否还有剩余尝试次数。如果有，利用试验反馈返回第 3 步。
7. 否则，选择最佳有效候选，或记录失败。
8. 保存最终输出和日志。

每次尝试后保留有效候选，避免后续失败丢失先前可用结果。一种简单起始策略是**总共最多尝试三次**。双遍编码计为一次尝试，但两遍耗时均需计入。若继续尝试不太可能带来改善，应提前停止。

### B1 最小环境

使用 NumPy、OpenCV 计算特征，Matplotlib 绘图，并用 Python 标准库 `subprocess`、`json`、`csv`、`pathlib`、`time`、`hashlib` 编排流程。调用模型 API 时可选用 Requests。

安装依赖并记录版本：

```bash
pip install numpy opencv-python matplotlib
pip freeze > requirements.txt
```

FFmpeg 和 ffprobe 需要单独安装，将其 `bin` 目录加入 Path，或配置绝对路径。使用以下命令检查构建。

```bash
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -h encoder=libx264
```

### B2 计算与调整码率

设 `S` 为原文件字节数，`r` 为目标比例，`T` 为时长，单位为秒。预算只取整到字节，不能取整到 MB。下式中 2% 的开销余量属于初始估计。

```python
target_bytes = floor(S * r)
video_bps = 0.98 * 8 * target_bytes / T
# If an output is too large / 输出超出预算时：
next_video_bps = video_bps * target_bytes / actual_bytes * 0.98
```

计算前需定义输入变量，并通过 `from math import floor` 导入取整函数。单位采用十进制：**1 MB = 1,000,000 bytes；1 kbps = 1,000 bit/s**。调整后重新编码原始输入。

### B3 双遍编码示例

替换 `INPUT`、`RATEk`、`JOB` 和 `OUT.mp4`。每次尝试使用唯一的 `JOB` 前缀，同一次尝试的两遍共用此前缀。以下每条命令均为一行。

```bash
ffmpeg -y -i INPUT -an -c:v libx264 -preset medium -pix_fmt yuv420p -b:v RATEk -pass 1 -passlogfile JOB -f null NUL
ffmpeg -y -i INPUT -an -c:v libx264 -preset medium -pix_fmt yuv420p -b:v RATEk -pass 2 -passlogfile JOB -movflags +faststart OUT.mp4
```

Python 中应向 `subprocess` 传入参数列表。macOS/Linux 使用 `/dev/null` 替换 `NUL`。不同候选使用不同输出路径，避免互相覆盖。

### B4 解码检查

```bash
ffmpeg -v error -xerror -i OUT.mp4 -map 0:v:0 -f null NUL
```

macOS/Linux 使用 `/dev/null`。检查返回码、时长、帧数和时间戳。该命令验证解码，不保存重建帧。

## 二、编码参数与可选模型

### C 编码设置和初始特征

初版可从码率控制和一种依赖内容的选择开始。其余设置先保留 preset 默认值，有明确理由后再测试。以下均为示例，不是强制配置。

| 参数 | 用途与起始建议 |
| --- | --- |
| `-c:v libx264` | 选择 x264 编码器，不表示质量等级。 |
| `-b:v` | 目标平均码率，例如 `2000k` 为 2 Mbps；仍需检查实际大小。 |
| `-pass 1` / `-pass 2` | 先分析，再根据统计分配比特；两遍均读取原始输入。 |
| `-crf` | 以质量为导向的替代控制方式。数值较低通常质量较高、文件较大，不保证大小。 |
| `-preset` | 控制搜索投入，可比较 `medium` 与 `slow`，同时记录质量和耗时。 |
| `-g` | 最大关键帧间隔，单位为帧。30 fps 时 60 帧约 2 秒；候选值 30、60、120。 |
| `-keyint_min` | 最小关键帧间隔控制，受 x264 规则约束；初期保留默认值。 |
| `-sc_threshold` | 场景切换灵敏度；较高值通常更容易插入切换，0 禁用检测；不是百分比阈值。 |
| `-bf` | 最大连续 B 帧数，可试 0、2、3；更多预测可能增加重排序延迟。 |
| `-refs` | 参考帧数量，可试 1、3、5；更多参考增加时间和内存成本。 |
| `-aq-mode` | 区域量化：0 关闭，1 基于方差，2 自动方差，3 带暗区偏置；可先比较 1 与 2。 |
| `-aq-strength` | AQ 分配强度，在同一模式下可试 0.8、1.0、1.2，观察不同区域的取舍。 |

灰度帧间平均绝对差可粗略反映时间变化，边缘像素比例可粗略反映细节。镜头移动、光照和噪声都会影响这两类信号。设置阈值前先查看时间线。

较小的决策空间便于解释，例如只在两种 preset 或两种 AQ 模式间选择，再比较大小、质量与成本。

### D1 其他可选编码参数

| 参数 | 用途与起始建议 |
| --- | --- |
| `-me_method` | 运动搜索方法，如 `hex`、`umh`；更全面的搜索可能改善预测，但增加成本。 |
| `-subq` | 亚像素和决策细化程度，例如 5、7、9；较高值通常更耗时。 |
| `-rc-lookahead` | 用于规划的前瞻帧数；仅在短片段中有用时比较 20 与 40。 |
| `-mbtree` | 根据未来预测重要性分配比特；初期保持启用。 |
| `-tune` | 内容相关的一组调整，如 `film`、`animation`；初期不覆盖。 |
| `-psy-rd` | 心理视觉优化，如 `1.0:0.0`；保留纹理可能与像素误差指标存在取舍。 |
| `-deblock` | 去块滤波偏移，如 `0:0`、`1:1`、`-1:-1`；较强滤波可能减轻块边缘，但使细节变软。 |
| `-maxrate` / `-bufsize` | VBV 码率和缓冲约束；`bufsize` 单位为 bit，而非 bit/s；均不保证最终文件大小。 |
| `-x264-params` | 一次传入多个 x264 参数，如 `"aq-mode=2:aq-strength=1.0"`；避免与其他选项重复设置。 |

### D2 可选 LLM 接口

向模型发送精简特征摘要、预算、允许的选项、尝试历史和剩余次数。结构化响应可以简化为：

```json
{
  "video_kbps": 2000,
  "preset": "medium",
  "aq_mode": 2,
  "reason": "Test regional allocation against the previous candidate."
}
```

示例理由意为“相对于前一个候选，测试区域比特分配”。执行前验证字段和范围，设置超时、有限重试及规则回退。密钥放在环境变量中，从日志中移除；记录供应商和模型 ID。示例数值只说明响应结构，不能直接视为通用配置。供应商可用性与限制需直接核查，项目不要求特定模型。纯规则控制器也可以使用相同的验证与日志接口。

### D3 DeepSeek 接入示例

1. 登录 [API 平台](https://platform.deepseek.com)，注册或登录账号。
2. 打开 [API keys 页面](https://platform.deepseek.com/api_keys)，创建密钥并供本地程序使用，同时检查余额和用量。密钥放在环境变量中，不写入代码或日志。
3. 从[官方文档](https://api-docs.deepseek.com/)选择模型，并将模型 ID 保存到 `DEEPSEEK_MODEL` 环境变量。
4. 使用匹配的密钥、base URL 和模型 ID。base URL 为 `https://api.deepseek.com`。

下面使用 OpenAI SDK 演示非流式调用。推理和思考参数应与所选模型匹配。

```python
# Please install OpenAI SDK first / 请先安装 OpenAI SDK：pip3 install openai
import os

from openai import OpenAI

client = OpenAI(
    api_key = os.environ.get('DEEPSEEK_API_KEY'),
    base_url = "https://api.deepseek.com",
)

response = client.chat.completions.create(
    model = os.environ["DEEPSEEK_MODEL"],
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

## 三、测量、复现与资料链接

### E1 一致的测量方式

参考视频和输出视频应按时间戳对齐，不能静默地只比较共有前缀。简单评价应保留输入分辨率和帧率；若发生变化，应说明对齐和重采样过程。

计算亮度 PSNR 时，先汇总所有对应像素和帧的平方误差，再取对数。完全一致时记为无穷大 PSNR。MS-SSIM 应记录实现、通道、数据范围、尺度和时间聚合方式。FFmpeg 普通 `ssim` 滤镜为单尺度。

```python
file_bitrate_bps = 8 * actual_file_bytes / duration_s
video_bitrate_bps = 8 * sum(video_packet_bytes) / duration_s
```

第二项使用 ffprobe 的视频包大小。整文件码率包含容器开销，两个指标应分列记录。

### E2 计时与日志

使用 `time.perf_counter()` 计量从读取元数据之前，到最终评价和日志完成之后的总耗时。计入全部尝试、双遍编码的两遍、API 等待与失败；不计安装、下载、人工开发和报告写作。存在阶段重叠时，不得按顺序执行的方式直接相加。

| 记录类别 | 建议字段 |
| --- | --- |
| 任务摘要 | `video_id`、`target_ratio`、`target_bytes`、`actual_bytes`、`output_path`、`status`、`failure_reason` |
| 质量与完整性 | `psnr_y_db`、`ms_ssim`、`decode_ok`、`duration_s`、`frame_count`、`actual_video_kbps` |
| 耗时与选择 | `total_time_s`、`encode_time_s`、`agent_time_s`、`eval_time_s`、`attempts`、`selected_attempt` |
| 每次尝试日志 | `job_id`、`attempt_id`、特征、参数、FFmpeg 参数列表、返回码、测量结果、下一步行动及原因 |

在运行配置中统一记录硬件、软件版本、线程数和缓存策略。计算输入、输出文件哈希用于追溯，原始日志保留完整数值精度。

### E3 批量测试前的小检查

检查参考视频与自身比较；主动触发一次超预算重试；如果使用 API，模拟一次无效模型响应。这些调试案例与正式实验结果分开保存。

### F 参考资源

使用与已安装软件版本匹配的文档。

| 类别 | 资源 |
| --- | --- |
| 安装 | [Python 下载](https://www.python.org/downloads/) |
| 安装 | [Python 虚拟环境](https://docs.python.org/3/library/venv.html) |
| 安装 | [FFmpeg 下载](https://ffmpeg.org/download.html) |
| 特征分析 | [OpenCV Python](https://pypi.org/project/opencv-python/) |
| 编码 | [FFmpeg libx264 参数](https://ffmpeg.org/ffmpeg-codecs.html#libx264_002c-libx264rgb) |
| 元数据 | [FFprobe 元数据与数据包检查](https://ffmpeg.org/ffprobe.html) |
| 质量 | [FFmpeg PSNR 滤镜](https://ffmpeg.org/ffmpeg-filters.html#psnr) |
| 质量 | [PyTorch MS-SSIM 实现](https://pypi.org/project/pytorch-msssim/) |
| 可选 API | [DeepSeek](https://api-docs.deepseek.com/) |
| 可选 API | [SiliconFlow](https://docs.siliconflow.cn/) |
| 可选 API | [OpenRouter](https://openrouter.ai/docs/quickstart) |
| 可选 API | [Groq](https://console.groq.com/docs/overview) |

模型 API 为可选项。使用前检查当前模型 ID、价格、访问条件和速率限制；MS-SSIM 需记录包版本及指标配置。

## 四、数据集与许可文件

### G1 视频清单

数据集包括 12 个无音轨视频、对应的 JSON 元数据、许可与来源文本，以及视频预览图。视频场景和开发、测试划分如下。

| 视频 | 预览画面 | 用途 |
| --- | --- | --- |
| `01_FourPeople.mp4` | 四人围桌而坐。 | 开发 |
| `02_Beauty.mp4` | 人物面部特写与飘动的头发。 | 开发 |
| `03_Bosphorus.mp4` | 水面船只，背景为桥梁和岸边。 | 开发 |
| `04_HoneyBee.mp4` | 紫色花丛。 | 开发 |
| `05_Jockey.mp4` | 赛道上的骑手和马。 | 最终测试 |
| `06_ShakeNDry.mp4` | 林间小路上的狗。 | 最终测试 |
| `07_Mobcal.mp4` | 细节丰富的船舶照片及周围图案。 | 开发 |
| `08_Shields.mp4` | 人物站在纹章盾牌墙前。 | 开发 |
| `09_Parkrun.mp4` | 积雪地面、水边与跑步者。 | 最终测试 |
| `10_Stockholm.mp4` | 城市建筑和滨水区域。 | 最终测试 |
| `11_Sintel.mp4` | 动画角色与飞行生物。 | 未指定 |
| `12_ControlledBurn.mp4` | 燃烧建筑、烟雾、树木及附近人物。 | 未指定 |

### G2 字节预算与初始码率

共同规格来自 JSON：1280 × 720、30 fps、无音轨、H.264 无损（libx264 QP 0）。`probe` 记录 `h264`、High 4:4:4 Predictive profile、`yuv420p`、8 bit、逐行扫描、16:9 显示比例、1:1 像素比例及 `1/15360` 时间基。除 ShakeNDry 为 75 帧外，其余为 150 帧。

大小预算为 `floor(bytes * ratio)`，初始视频码率为 `0.98 * 8 * target_bytes / duration / 1000`，单位为 kbps。下表码率保留三位小数，用作编码起点；实际文件大小和码率需在编码后测量。

| 视频 | 时长 s | 原字节数 | 5% 字节预算 | 5% 初始 kbps | 2% 字节预算 | 2% 初始 kbps |
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

### G3 来源与截取起点

`start_seconds` 表示从源素材开始截取的时间，单位为秒。

| 视频 | 来源标记 | 起点 s | 原素材 |
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

### G4 完整元数据

元数据包括文件属性、SHA-256、流和容器信息、标签、disposition 标志及编码器版本。`bytes` 表示文件字节数，`duration` 表示时长，`fps` 表示帧率，`audio` 表示是否有音轨，`sha256` 为校验值，`probe.streams` 和 `probe.format` 分别描述流与容器。

<details>
<summary>01_FourPeople.json</summary>

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

### H1 许可与来源文本译文

各视频的使用条件和署名要求如下，完整许可文本见 H2。

#### Beauty、Bosphorus、HoneyBee、Jockey、ShakeNDry

对应 `Beauty_Copyright.txt`、`Bosphorus_Copyright.txt`、`HoneyBee_Copyright.txt`、`Jockey_Copyright.txt`、`ShakeNDry_Copyright.txt` 五份文件，内容相同：该视频序列及全部相关知识产权仍归 Digiturk 所有；可依照 [Creative Commons 署名—非商业性使用 3.0 未本地化版本](http://creativecommons.org/licenses/by-nc/3.0/deed.en_US)使用。

#### FourPeople_source.txt

- 名称：FourPeople。
- 来源：<https://media.xiph.org/video/derf/>。
- 发布者将 FourPeople 标记为公有领域。
- 下载地址：<https://media.xiph.org/video/derf/y4m/FourPeople_1280x720_60.y4m>。
- 记录的访问日期：2026-10-25。
- 教学衍生版本：截取第 1–6 秒，720p、30 fps、无音轨、H.264 无损。

#### Sintel_attribution.txt

Sintel 预告片摘录，版权为 Blender Foundation，网站为 <https://durian.blender.org>。采用 [Creative Commons 署名 3.0](https://creativecommons.org/licenses/by/3.0/)，发布者许可及署名说明见 <https://durian.blender.org/sharing/>。

源文件为 <https://media.xiph.org/video/derf/y4m/sintel_trailer_2k_720p24.y4m>。教学衍生版本为 5 秒无音轨片段，720p，通过重复帧将 24 fps 转为 30 fps，使用 H.264 无损编码。

#### NTIA_HDTV_Readme.txt

这些视频序列归美国联邦政府机构 NTIA/ITS 所有，于 2008 年在项目 3141012-300“Video Quality Research”下制作。仅限研究用途。接受这些条款并明确同意在复制或衍生作品中保留此文本、适当注明 NTIA/ITS 所有权后，可使用、复制、修改和再分发。

文件分三组说明原素材。

| 组别 | 原素材规格与设备 | 编辑与场景 |
| --- | --- | --- |
| 第一组 | 1080p、30 fps；Panasonic AJ-HDX-900，保存至 DVCPro 磁带；视频标准标记为 Native。 | 19 秒片段，计划去掉开头和结尾各 2 秒。场景：Aspen、RedKayak、WestWindEasy。 |
| 第二组 | 1080p、30 fps；Panasonic P2HD AJ-HPX3000G，Fujinon TV Lens HA22x7.8 BERM-M48；相机以 100 Mbps H.264 帧内编码记录；视频标准为 Native。 | 19 秒片段，计划去掉首尾各 2 秒。RushFieldCuts 快门 30；SnowMnt 快门 30；SpeedBag 快门 60；TouchdownPass 快门 30。 |
| 第三组 | 1080p、30 fps；Sony HVR-Z1U（HDV 格式），转换为 SMPTE 292M 高清 1080i 格式，录制到 Panasonic HD-D5；视频标准为 Native；再次注明仅限研究。 | 19 秒片段，计划去掉首尾各 2 秒。ControlledBurn 场景，说明为对一所曾用于制造甲基苯丙胺的房屋进行受控燃烧时拍摄的火灾视频。 |

上述为上游素材说明，不代表本地教学片段仍为 19 秒或 1080p。本地规格见 G2。

#### SVT_720p_ReadMe.txt

SVT 源序列及场景说明如下。

| 源序列 | 帧数 | 场景说明 |
| --- | --- | --- |
| `720p50_mobcal_ter` | 504，含 4 帧中灰帧 | 类似 Mobile&Calendar 的近景：移动的文字日历、瓦萨号船舶细节照片、带彩色玩具的移动火车；背景有细节丰富的棕色墙纸和绘有图形的黄色墙纸。细节非常多，通常编码难度较高。 |
| `720p50_parkrun_ter` | 504，含 4 帧中灰帧 | 远景：男子手持雨伞在公园跑步，背景有树木、积雪和水。细节多、编码要求高。 |
| `720p50_stockholm_ter` | 504，含 2 帧中灰帧 | 横摇展示斯德哥尔摩老城，可见建筑、水面和移动车辆。 |
| `720p50_shields_ter` | 504，含 2 帧中灰帧 | 留胡须、穿斑点外套的男子走过细节丰富的骑士盾牌墙，序列末尾变焦。 |
| `720p5994_parkrun_ter` | 604，含 4 帧中灰帧 | 同上公园跑步远景：雨伞、树木、积雪和水。 |
| `720p5994_stockholm_ter` | 604，含 2 帧中灰帧 | 同上斯德哥尔摩老城横摇。 |
| `720p5994_shields_ter` | 604，含 2 帧中灰帧 | 同上男子经过盾牌墙，末尾变焦。 |

拍摄设备为 Thomson LDK6000，相机镜头为 Canon HJ9X5.5KLL-SC 变焦镜头；使用 DVS HDStationPlus，以原生 10 bit 4:2:2 记录，存储于 DVS HDStationPlus Diskrecorder。技术信息列出 50 fps 逐行、1280 × 720、4:2:0 色度抽样，以及 SMPTE 296M 色彩转换。

子采样滤波系数为：

```text
-0.0063 / 0 / 0.0299 / 0 / -0.0831 / 0 / 0.3098 / 0.4994 / 0.3098 / 0 / -0.0831 / 0 / 0.0299 / 0 / -0.0063
```

素材联系人为 Lars.Haglund@svt.se，另列 <http://www.svt.se/svtinfo/inenglish/dev/> 及 <http://www.svt.se/svtinfo/inenglish/dev/svt_widexga_final.pdf>。用途限制写为“No restrictions”，版权写为“No copyright”。制作方为 SVT Sveriges Television AB、Lars Haglund，摄影为 Jan-Hugo Norman & Team。全部素材由 SVT Sveriges Television AB 于 2001 年 12 月拍摄。

### H2 许可与来源英文原文

以下为九份完整许可及来源记录，包含设备信息和使用条件。

#### Beauty_Copyright.txt

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### Bosphorus_Copyright.txt

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### FourPeople_source.txt

```text
FourPeople
Source: https://media.xiph.org/video/derf/
The publisher labels FourPeople as public domain.
Download: https://media.xiph.org/video/derf/y4m/FourPeople_1280x720_60.y4m
Accessed: 2026-10-25
Teaching derivative: seconds 1-6, 720p, 30 fps, silent, H.264 lossless.
```

#### HoneyBee_Copyright.txt

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### Jockey_Copyright.txt

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### NTIA_HDTV_Readme.txt

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

```text
This sequence and all intellectual property rights therein remain the property of Digiturk.
You may use this sequence according to Creative Commons Attribution-NonCommercial 3.0 Unported (http://creativecommons.org/licenses/by-nc/3.0/deed.en_US).
```

#### Sintel_attribution.txt

```text
Sintel trailer excerpt
Copyright Blender Foundation | https://durian.blender.org
Creative Commons Attribution 3.0: https://creativecommons.org/licenses/by/3.0/
Publisher license and attribution: https://durian.blender.org/sharing/
Source: https://media.xiph.org/video/derf/y4m/sintel_trailer_2k_720p24.y4m
Teaching derivative: 5-second silent excerpt, 720p, frame repetition from 24 to 30 fps, H.264 lossless.
```
