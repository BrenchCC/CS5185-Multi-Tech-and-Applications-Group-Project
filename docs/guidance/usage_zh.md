# 内容自适应视频编码实验台使用指南

本指南从准备输入到核对交付文件，介绍英文终端界面和命令行的完整操作。两种入口共用同一套编码、决策和评价服务。运行命令时请先进入项目根目录；[中文 README](../../README_ZH.md) 提供完整项目入口，[英文方法说明](../adaptive_encoding_method.md)记录特征、校准与指标算法。

**🧭 建议阅读顺序：**准备环境与数据 → 选择策略并运行 → 查看输出与指标 → 按需复现实验。

> 💡 **第一次使用？** 先完成数据预检，再使用仓库提供的冻结规则运行一条视频，无需配置模型密钥或重新校准。

## 🛠️ 一、运行前准备

### 1.1 安装工具和依赖

准备 Python 3.10，以及可从 `PATH` 调用的 FFmpeg、ffprobe。FFmpeg 必须包含 `libx264`。在已激活的 Python 环境中执行：

```bash
ffmpeg -version
ffprobe -version
ffmpeg -hide_banner -h encoder=libx264
pip install -r requirements.txt
python main.py --help
```

`requirements.txt` 安装 Python 包，不安装 FFmpeg。若编码器查询没有显示 libx264，请先安装或切换到包含该编码器的 FFmpeg 构建。程序使用 OpenCV 提取特征，使用 PyTorch 与 `pytorch-msssim` 计算五尺度指标；具体软件版本由运行记录保存。

### 1.2 放置和预检课程数据

将 12 个课程原始 MP4 直接放在根目录 `CS5185_Project_Video_Dataset/`，并在 `metadata/` 下保留每个视频的同名 JSON。例如 `01_FourPeople.mp4` 对应 `metadata/01_FourPeople.json`。保留课程视频原始文件、元数据和来源许可；视频素材不属于本项目代码许可。

```bash
python main.py check
```

检查会确认 libx264，并用 ffprobe 与元数据核对 12 条输入的 SHA-256、文件大小、宽高、帧数、时长、30 fps、`yuv420p` 和无音轨约束。成功后命令打印 `runs/<时间戳>_check/`，其中 `input_check.json` 保存环境与输入信息。预检读取所有输入，不对保留集编码；遇到哈希、大小或元数据不匹配时，应恢复对应课程原片，而不是修改元数据来绕过检查。

开发集为 **01、02、03、04、07、08**；保留集为 **05、06、09、10、11、12**。TUI 的单视频下拉框只列开发视频。命令行可指定任意输入路径，因此执行者仍需自行维护实验划分。

### 1.3 配置可选的 Ark LLM

固定基线和纯规则策略无需 API 配置。要使用模型，可先检查本地是否已有 `.env`；首次配置时在项目根目录将 `.env.example` 复制为 `.env`，填写自己的变量：

| 变量 | 用途 |
| --- | --- |
| `LLM_API_KEY` | Ark API 密钥。 |
| `LLM_ENDPOINT` | 模型推理接入点。 |
| `LLM_API_BASE_URL` | 可选 API 根地址；不设置时使用程序内默认方舟地址。 |

例如，确认目标文件不存在时可使用 `cp -n .env.example .env` 创建，再用编辑器填写。不要覆盖已有配置，也不要把 `.env`、密钥或包含凭据的终端输出放入提交材料。程序读取项目根目录的 `.env`；同名环境变量优先于该文件。

[提示词](../../prompts/encoding_decision_zh.md)要求模型从 `medium`/`slow` 和整数 AQ 1/2 中选择，并返回简短英文理由。程序将数值特征、预算、当前码率和此前尝试摘要发给模型；若存在规则参考，也会传递参考 preset 和 AQ。视频、图像帧、原视频路径及密钥不作为提示内容发送。Ark LLM 是可选的在线服务，执行到模型轮次会产生真实请求和适用费用。

## 🚀 二、选择入口与策略

### 2.1 五种策略

| 策略和界面名称 | 轮次顺序 | 规则文件 | Ark 请求 |
| --- | --- | --- | --- |
| `baseline_medium` / **Fixed medium / AQ 1** | 每轮 medium/AQ 1 | 不需要 | 无 |
| `baseline_slow` / **Fixed slow / AQ 1** | 每轮 slow/AQ 1 | 不需要 | 无 |
| `rule` / **Rule only** | 每轮冻结规则 | 需要 | 无 |
| `llm` / **LLM only** | 每轮 LLM | 不需要 | 每个执行到的轮次最多一次 |
| `hybrid` / **Default** | 规则、规则、LLM | 需要 | 仅到达第三轮时 |

默认是 `hybrid`。每项任务最多三轮，每轮选择一次参数，双遍编码合计一次尝试；第一个通过预算、完整性和评价检查的输出结束任务。固定基线与规则的重试通常沿用相同参数并降低码率；LLM 轮可以结合此前摘要重新选择允许的参数。

项目提供可直接使用的冻结规则 `experiments/full_exps/policy.json`；命令行默认规则路径是 `runs/policy.json`。不在默认位置时，应在 TUI 的 **Frozen policy file** 或 CLI 的 `--policy` 中明确指定。当前冻结策略统一使用 medium，平均边缘密度不超过 0.10101047 选择 AQ 2，其余选择 AQ 1。

### 2.2 通过终端界面运行

```bash
python main.py
```

界面为英文。F1、F2、F3 分别进入 **Task Setup**、**Run Monitor** 和 **Results**；可使用 Tab/Shift+Tab、方向键、Enter 或鼠标操作。约 110 列 × 42 行的终端更易查看，小窗口可以滚动。

1. 打开 **Environment & Data**，确认数据目录，点击 **Check environment**。程序会检查全部 12 条原片。
2. 在 **Task Setup** 选择开发视频和 5% 或 2% 预算。若使用仓库已有冻结规则，将 **Frozen policy file** 设为 `experiments/full_exps/policy.json`。
3. 在 **Decision strategy** 选择策略，点击 **Run selected**。要先排除 API 配置问题，可选择固定基线或 **Rule only**。
4. 在 **Run Monitor** 查看视频、轮次、双遍进度和日志。点击 **Cancel run** 请求取消；若模型同步请求正在进行，程序等待该请求返回或超时后再检查取消状态。
5. 完成后在 **Results** 加载运行目录，选择行查看参数、理由及状态；**Export CSV** 将该目录的结果汇总到 `summary.csv`。运行中按 `q` 或 Ctrl+C 退出时，会出现停止确认。

**Calibrate rules** 启动 48 项开发集候选配置；**Validate dev set** 使用选定策略文件，运行 36 项固定基线和规则对照。两项都不是由单视频策略下拉框决定的模型实验。任务顺序执行；取消后保留已完成记录，重新启动会创建新目录，并不自动续跑。

### 2.3 通过命令行运行

先使用自带规则编码一条视频：

```bash
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.02 --strategy rule --policy experiments/full_exps/policy.json
```

成功时返回码为 0，并打印类似 `runs/<时间戳>_single/` 的目录；失败任务返回非零状态。`--ratio` 只接受 `0.05` 和 `0.02`。下列命令分别演示固定基线、默认轮次和纯模型策略：

```bash
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.05 --strategy baseline_medium
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.02 --strategy hybrid --policy experiments/full_exps/policy.json
python main.py run --input CS5185_Project_Video_Dataset/01_FourPeople.mp4 --ratio 0.02 --strategy llm
```

后两条在进入 LLM 轮次时可能发出真实请求。`--dataset` 可指定数据根目录，`--output` 可指定运行输出根目录，`--policy` 用于选择规则文件。若无命令参数，`python main.py` 启动界面；命令列表可通过 `python main.py --help` 查看。

## 📊 三、校准、验证与全量实验

### 3.1 开发集校准与独立验证

```bash
python main.py calibrate
python main.py batch --policy runs/policy.json
```

校准对六条开发视频的两档预算执行 medium/slow × AQ 1/2，共 48 个候选配置。程序搜索常量或单阈值规则，记录按视频留一结果，并写入本次运行目录及输出根目录下的 `policy.json`。

`batch` 使用冻结策略重新执行六视频 × 两档预算 × 三组对照，共 36 项；它不复用校准编码结果。校准与验证开始前都会预检 12 条输入，但编码任务仅使用开发集。若校准改用其他 `--output`，生成的规则也位于该输出根目录；后续应显式设置 `--policy`。

### 3.2 12 条视频全量对照

```bash
python experiments/full_exps/run.py
python experiments/full_exps/run.py --execute
```

> ⏱️ **执行范围：**第一条只预检原片、仓库冻结策略及预登记矩阵；第二条预检后开始实际编码。

全量脚本使用默认课程数据目录，按 12 视频 × 两档预算 × 固定 medium、固定 slow、冻结规则三组执行，共 72 项。每组 24 项，不调用 API；该任务耗时和磁盘使用量明显高于单视频运行。执行完成后，在打印的 `runs/<时间戳>_full_exps/` 检查队列、任务和图表。

已有全量记录为 72/72 项满足大小并通过全片检查，55 项首轮达标、17 项第二轮达标。三个单独的 Ark 案例不计入这 72 项；其实际状态和预算限制见[全量实验说明](../../experiments/full_exps/README.md)与[逐片分析](../../experiments/full_exps/report_analysis_zh.md)。项目报告、实验报告和提交范围分别见[报告索引](../../reports/README.md)和[打包指南](../submission/packaging_guide_zh.md)。

## 🔎 四、查看进度与核对输出

### 4.1 单次尝试的过程

每轮先确定 preset、AQ 和目标视频码率。两遍 FFmpeg 都从原片读取数据，使用相同参数和独立 pass 日志；输出为 MP4。程序检查输出大小、完整解码和序列对齐，并计算全片亮度质量。完整 MP4 超限时，依据目标与实际大小之比下调下一轮码率并留出余量。两遍计一次编码尝试，结果在第一项有效输出处停止。

模型请求或 JSON 参数校验出错时，该轮状态为 `decision_failed`，若还有轮次则按预定策略继续；不会隐式回退到其他控制器。FFmpeg 进程、完整性或指标计算出现硬错误时，任务结束并保留原因。超过三轮仍无有效输出时，最终任务状态为失败。

### 4.2 文件和字段

结果的位置由运行命令打印；默认根目录为 `runs/`。实际文件取决于使用的是单任务、校准还是批量工作流：

| 文件 | 核对内容 |
| --- | --- |
| `input_check.json` | 已执行预检时的输入与软件检查结果。 |
| `manifest.json`、`source/` | 环境信息、相关代码和提示词快照。 |
| `queue.json` | 批量任务队列和状态。 |
| `summary.csv` | 本运行的策略、状态、大小、画质和耗时汇总。 |
| `task.json` | 目标、状态、`selected_attempt`、`output_path`、轮次及失败原因；单任务位于 `task/task.json`。 |
| `features.json` | 逐帧特征、均值和第 90 百分位数。 |
| `attempt_N/attempt.json` | 决策、目标码率、参数数组、返回码、大小、指标与调整原因。 |
| `attempt_N/pass_1.log`、`pass_2.log` | 实际进入对应编码遍次时的 FFmpeg 输出。 |
| `evidence/` | 校准或批量对照完成后导出的特征曲线和同帧对照图。 |

判断交付文件时先查看 `task.json`：`status` 应为 `success`，`actual_bytes` 不超过 `target_bytes`，并通过 `selected_attempt` 和 `output_path` 定位被接受的 MP4。不要只按目录中是否存在 MP4 判断成功：失败或超预算尝试也可能留下输出。

每轮的 `llm` 审计可能包含提示词哈希、请求摘要、响应模型、token 用量、耗时和校验状态；异常提前发生时部分字段缺失。模型理由解释选参思路，不能替代文件大小、画质和完整性检查。

为已有运行重新生成汇总时，替换下方目录占位符：

```bash
python main.py summarize --folder runs/EXISTING_RUN_DIRECTORY
```

### 4.3 如何解释质量与耗时

系统先验证完整解码、宽高、帧数、帧率、时长和相对时间戳，再在原分辨率的原生解码 Y 平面比较完整序列。Y-PSNR 由全片亮度像素均方误差换算；五尺度 Y-MS-SSIM 逐帧计算再取平均。普通单尺度 SSIM 不代替 MS-SSIM。两个指标分别衡量不同性质，也不能单独证明观看体验。

目标大小按原文件字节数取整数百分比向下取整；实际比较的是包含封装开销的完整 MP4。编码时间累计所有尝试的双遍时间；总时间还包括特征、决策、检查和评价。策略比较应配对同视频、同预算，并同时查看最终文件大小、参数与重试次数；单次耗时不构成跨硬件性能结论。具体公式和尺度参数见[方法说明](../adaptive_encoding_method.md)。

## 🧰 五、常见问题与复现

### 5.1 预检、规则和界面

- **找不到 libx264 或 ffprobe：**确认系统 FFmpeg 构建支持 libx264，并检查当前终端的 `PATH`。
- **预检报告文件数量、哈希或大小错误：**核对课程数据是否有 12 个 MP4、同名元数据和未改动的原始字节。
- **找不到规则：**在界面中选择 `experiments/full_exps/policy.json`，或完成校准后使用输出根目录下的 `policy.json`。`llm` 和固定基线不需要规则。
- **无法选中保留视频：**界面下拉框限定开发集；命令行可通过 `--input` 显式指定文件，并由执行者负责实验边界。
- **无明确百分比的阶段：**特征提取、决策、评价等阶段显示活动状态；仅 FFmpeg 编码阶段使用实际进度。

### 5.2 模型请求和 JSON

- **`Ark request failed`：**检查密钥是否配置、接入点与 API 根地址是否匹配、网络和服务状态；不要打印或分享密钥。查看 `attempt.json` 中的 `llm.api_error_type`、可能存在的 `llm.api_error_causes` 和 `elapsed_s`。旧记录可能只有顶层异常。
- **连接或超时：**可在不泄露凭据的前提下排查当前终端网络和代理。匿名模型列表请求返回 HTTP 401 只说明收到了 HTTP 响应，不代表指定推理接入点已通过认证。
- **JSON 校验不通过：**检查是否只有一个对象，字段是否严格为 `preset`、`aq_mode`、`reason`，preset 是否在白名单、AQ 是否为整数 1 或 2。解析器接受裸 JSON 或单个 JSON 围栏，拒绝混入解释、多对象、重复键和非法数字等情况。
- **默认策略没有调用模型：**查看前两轮状态；规则轮已经达标时，程序会提前停止。

### 5.3 测试和复现

```bash
pip install pytest==9.0.3
python -m pytest -q
```

自动测试覆盖预算、参数验证、重试、完整性、取消与终端交互等路径；模拟测试不是实际编码或模型请求证据。下面的可选验证会使用真实课程视频编码并新建运行目录：

```bash
python tests/verify_real_pipeline.py
```

复现实验时，保存或核对原片哈希、冻结策略、提示词、软件环境、参数、各轮记录及最终输出。开发集已参与规则校准，不能将其验证结果当作独立保留集表现。需要提交可播放视频时，应单独按课程要求提供；报告里的截图不能替代 MP4。
