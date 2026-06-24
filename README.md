# estim-bci-paradigm

单机患者端评分和录音程序。程序录入 VAS-D 评分后启动麦克风录音，并保存评分与音频数据。

## Files

- `patient.py`: 单机患者端入口，负责评分录入、麦克风录音和本地保存。
- `patient_config.toml`: 患者端运行配置。
- `common.py`: 配置加载和 PsychoPy 界面组件。

每次运行会在 `data/` 下创建一个会话目录，包含 `ratings.csv` 和按编号保存的音频文件，如 `0001.wav`。

## Setup

```powershell
uv sync
```

## Run

```powershell
uv run .\.venv\Scripts\python.exe .\patient.py
```

程序启动后会先检测并显示可用麦克风；选择本次使用的麦克风后输入被试编号，再按界面完成连续评分和录音：

1. 在麦克风检测窗口中选择本次录音使用的麦克风。
2. 拖动滑块选择 VAS-D 评分。
3. 点击“确认评分”后自动开始麦克风录音。
4. 点击“停止并保存”写入当前编号的音频文件，如 `0001.wav`。
5. 程序自动进入下一条记录，编号从 `0001` 开始递增；完成后点击“结束”。

## Configuration

`patient_config.toml` 可配置全屏/窗口尺寸、显示器、评分范围、音频采样率、通道数、最大录音时长和字体。修改后重新运行程序生效。
