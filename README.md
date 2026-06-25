# estim-bci-paradigm

单机患者端评分和录音程序。程序录入 VAS-D 评分后启动麦克风录音，并保存评分与音频数据。

## Files

- `patient.py`: 单机患者端入口，负责评分录入、麦克风录音和本地保存。
- `lsl_marker_to_uart.py`: LSL marker 接收、打印与 UART 转发脚本。
- `start_components.bat`: Windows 一键启动脚本，先启动 LSL->UART 桥接，再启动患者端。
- `patient_config.toml`: 患者端运行配置。
- `lsl_markers.toml`: LSL marker stream 配置。
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

Windows 一键启动两个组件：

```bat
start_components.bat
```

运行前请先确认 `lsl_markers.toml` 的 `[uart].port` 和 `[uart].baudrate` 已设置为实际串口参数。脚本会先启动 LSL->UART 桥接组件；如果串口连接失败，患者端不会启动。

接收 LSL marker 并通过 UART 转发：

```powershell
uv run python .\lsl_marker_to_uart.py
```

脚本会先读取 `lsl_markers.toml` 中的 `[uart]` 配置并建立串口连接；连接失败则直接退出，不再等待 LSL stream。

每个接收到的 LSL 值会通过 UART 发送两个字节：`[0x36, data]`。

程序启动后会先检测并显示可用麦克风；选择本次使用的麦克风后输入被试编号，再按界面完成连续评分和录音：

1. 在麦克风检测窗口中选择本次录音使用的麦克风。
2. 拖动滑块选择 VAS-D 评分。
3. 点击“确认评分”后自动开始麦克风录音。
4. 点击“停止并保存”写入当前编号的音频文件，如 `0001.wav`。
5. 程序自动进入下一条记录，编号从 `0001` 开始递增；完成后点击“结束”。

程序运行时会创建单通道 8-bit integer 类型的 LSL stream。范式程序开始/结束会发送 `lsl_markers.toml` 中配置的 marker 值；点击“确认评分”时发送当前 VAS-D 分值。VAS-D 评分范围为 0-10。

## Configuration

`patient_config.toml` 可配置全屏/窗口尺寸、显示器、评分范围、最大录音时长和字体。`lsl_markers.toml` 可单独配置 LSL stream 元信息、范式开始/结束 marker 值和 UART 参数。修改后重新运行程序生效。
