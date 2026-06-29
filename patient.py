# -*- coding: utf-8 -*-
"""
患者端：录入 VAS-D 评分，随后录制麦克风音频并保存本地数据。
"""

import csv
import datetime
import os
import sys

import soundfile
from loguru import logger as LOGGER
from psychopy import core, event, gui, visual
from psychopy.hardware.microphone import MicrophoneDevice
from psychopy.sound.microphone import Microphone
from pylsl import StreamInfo, StreamOutlet, local_clock

import common
from common import (
    COL_BTN, COL_BTN_END, COL_BTN_END_HOVER, COL_BTN_HOVER, SCREEN_INDEX,
    Button, ClickDispatcher, fmt_score, fmt_time, make_text, make_window,
)

CFG = common.init_config(
    "patient_config.toml",
    {
        "rating": {"min": 0, "max": 10, "step": 1},
        "audio": {"max_recording_s": 300},
    },
)
LSL_CFG = common.load_config(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "lsl_markers.toml"),
    {
        "stream": {
            "enabled": True,
            "name": "VASDScoreMarkers",
            "type": "Markers",
            "source_id": "estim-bci-paradigm-vasd-score",
        },
        "markers": {},
    },
)

DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
MAX_RECORDING_S = float(CFG["audio"]["max_recording_s"])
RATING_MIN = float(CFG["rating"]["min"])
RATING_MAX = float(CFG["rating"]["max"])
RATING_STEP = float(CFG["rating"]["step"])
RATING_TICKS = [
    RATING_MIN + (RATING_MAX - RATING_MIN) * step / 5
    for step in range(6)
]
RATING_LABELS = None
RATING_ANCHORS = ["无抑郁", "中等抑郁", "最严重抑郁"]
SLIDER_POS = (0, -0.02)
SLIDER_SIZE = (1.35, 0.07)

STATE_RATING = "rating"
STATE_RECORDING = "recording"


def lsl_int8_value(value, label):
    value = int(round(float(value)))
    if not 0 <= value <= 127:
        raise ValueError(f"{label}={value} 超出 LSL int8 非负 marker 范围 0-127")
    return value


class LSLMarkerSender:
    def __init__(self, cfg):
        self.enabled = bool(cfg["stream"].get("enabled", True))
        self.markers = dict(cfg.get("markers", {}))
        self.outlet = None
        if not self.enabled:
            LOGGER.info("LSL marker stream 已禁用")
            return

        info = StreamInfo(
            str(cfg["stream"]["name"]),
            str(cfg["stream"]["type"]),
            1,
            0,
            "int8",
            str(cfg["stream"]["source_id"]),
        )
        self.outlet = StreamOutlet(info)
        LOGGER.info(
            "LSL marker stream 已创建：name={}, type={}, source_id={}",
            cfg["stream"]["name"],
            cfg["stream"]["type"],
            cfg["stream"]["source_id"],
        )

    def wait_for_consumer(self, timeout_s=5.0):
        if self.outlet is None:
            return False
        connected = self.outlet.wait_for_consumers(timeout_s)
        if connected:
            LOGGER.info("LSL receiver 已连接")
        else:
            LOGGER.warning("等待 LSL receiver 超时，仍会继续发送 marker")
        return connected

    def send_marker(self, marker_name):
        if self.outlet is None:
            return
        if marker_name not in self.markers:
            LOGGER.warning("LSL marker 未配置：{}", marker_name)
            return
        value = lsl_int8_value(self.markers[marker_name], marker_name)
        self.outlet.push_sample([value], local_clock())
        LOGGER.info("LSL marker：{}={}", marker_name, value)

    def send_score(self, score):
        if self.outlet is None:
            return
        value = lsl_int8_value(score, "VAS-D score")
        self.outlet.push_sample([value], local_clock())
        LOGGER.info("LSL VAS-D score：{}", value)


def setup_logging(session_dir):
    log_path = os.path.join(session_dir, "patient.log")
    log_format = "{time:YYYY-MM-DD HH:mm:ss.SSS} [{level}] {message}"
    LOGGER.remove()
    # 关闭 loguru 的 backtrace/diagnose：默认会把每个栈帧的变量值都 dump 出来，
    # 一个普通异常会刷出几十行，这里只保留简洁的标准栈信息。
    LOGGER.add(
        log_path, level="INFO", format=log_format,
        encoding="utf-8", enqueue=False,
        backtrace=False, diagnose=False,
    )
    LOGGER.add(sys.stderr, level="INFO", format=log_format, enqueue=False,
               backtrace=False, diagnose=False)
    return log_path


def describe_microphone(device):
    return (
        f"{device.deviceIndex}: {device.deviceName} "
        f"({device.hostAPIName}, {device.inputChannels}通道, "
        f"{int(device.defaultSampleRate)}Hz)"
    )


def is_real_microphone(device):
    # WASAPI 回环（Loopback）设备会以「输入设备」身份出现，但录的是系统播放的声音，
    # 静音时没有数据流，会反复报“gone to sleep”，无法当作麦克风使用，需排除。
    if int(getattr(device, "inputChannels", 0)) <= 0:
        return False
    name = str(getattr(device, "deviceName", "")).lower()
    return "loopback" not in name


def detect_microphone():
    try:
        devices = [
            device for device in MicrophoneDevice.getDevices()
            if is_real_microphone(device)
        ]
    except Exception as err:
        dlg = gui.Dlg(title="麦克风检测")
        dlg.addText(f"麦克风检测失败：{err}")
        dlg.show()
        return None

    if not devices:
        dlg = gui.Dlg(title="麦克风检测")
        dlg.addText("未检测到可用麦克风，请连接或启用麦克风后重新运行程序。")
        dlg.show()
        return None

    choices = [describe_microphone(device) for device in devices]
    dlg = gui.Dlg(title="麦克风检测")
    dlg.addText("检测到以下可用麦克风，请选择本次录音使用的设备。")
    dlg.addField("麦克风", choices=choices, initial=choices[0])
    result = dlg.show()
    if not dlg.OK or result is None:
        return None

    selected_label = result[0]
    return devices[choices.index(selected_label)]


def ask_subject_info():
    info = {"被试编号": "S001"}
    dlg = gui.DlgFromDict(dictionary=info, title="评分录音 - 被试信息",
                          order=["被试编号"])
    if not dlg.OK:
        return None
    return info


def open_session(subject_info):
    os.makedirs(DATA_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    session_dir = os.path.join(DATA_DIR, f"{subject_info['被试编号']}_{stamp}")
    os.makedirs(session_dir, exist_ok=True)
    csv_path = os.path.join(session_dir, "ratings.csv")
    csv_file = open(csv_path, "w", newline="", encoding="utf-8-sig")
    writer = csv.writer(csv_file)
    writer.writerow([
        "被试编号", "编号", f"{common.RATING_NAME}评分",
        "评分提交时间", "录音开始时间", "录音结束时间", "录音时长(s)", "音频文件",
    ])
    csv_file.flush()
    return session_dir, csv_file, writer


def make_microphone(device):
    # 按设备原生采样率与声道数录制：MicrophoneDevice.open() 内部本就强制使用设备的
    # inputChannels，请求其它值会被静默覆盖；这里显式对齐，支持单/多声道设备。
    sample_rate = int(device.defaultSampleRate)
    channels = int(device.inputChannels)
    max_samples = max(1, int(sample_rate * MAX_RECORDING_S))
    return Microphone(
        device=device.deviceIndex,
        sampleRateHz=sample_rate,
        channels=channels,
        maxRecordingSize=max_samples,
        policyWhenFull="warn",
        recordingExt="wav",
    )


def rating_fraction(rating):
    if rating is None or RATING_MAX == RATING_MIN:
        return 0
    return max(0, min(1, (float(rating) - RATING_MIN) / (RATING_MAX - RATING_MIN)))


def quantize_rating(rating):
    if rating is None:
        return None
    rating = max(RATING_MIN, min(RATING_MAX, float(rating)))
    if RATING_STEP > 0:
        rating = round((rating - RATING_MIN) / RATING_STEP) * RATING_STEP + RATING_MIN
    return max(RATING_MIN, min(RATING_MAX, rating))


def slider_live_rating(slider):
    marker = slider.getMarkerPos()
    if marker is not None:
        return quantize_rating(marker)
    return quantize_rating(slider.getRating())


def main():
    microphone_device = detect_microphone()
    if microphone_device is None:
        core.quit()

    subject_info = ask_subject_info()
    if subject_info is None:
        core.quit()

    session_dir, csv_file, writer = open_session(subject_info)
    log_path = setup_logging(session_dir)
    LOGGER.info("会话开始：subject={}, session_dir={}, log={}",
                subject_info["被试编号"], session_dir, log_path)
    lsl_sender = LSLMarkerSender(LSL_CFG)
    lsl_sender.wait_for_consumer()
    lsl_sender.send_marker("paradigm_start")
    LOGGER.info("麦克风：{}", describe_microphone(microphone_device))
    mic = make_microphone(microphone_device)
    # 流式写盘需与设备原生参数一致（make_microphone 也据此创建麦克风）。
    sample_rate = int(microphone_device.defaultSampleRate)
    channels = int(microphone_device.inputChannels)
    LOGGER.info("录音参数：sample_rate={}, channels={}, max_recording_s={}",
                sample_rate, channels, MAX_RECORDING_S)

    win = make_window("患者端", SCREEN_INDEX)
    win.mouseVisible = True
    mouse = event.Mouse(win=win)
    dispatcher = ClickDispatcher(win, mouse)

    count_text = make_text(win, "", pos=(0, 0.32), height=0.045,
                           color="#cccccc")
    rate_title = make_text(win, f"请进行 {common.RATING_NAME} 评分",
                           pos=(0, 0.22), height=0.07, bold=True)
    slider = visual.Slider(
        win, ticks=RATING_TICKS,
        labels=RATING_LABELS,
        pos=SLIDER_POS, size=SLIDER_SIZE, granularity=RATING_STEP,
        style="slider",
        color="white", fillColor="#9fd3ff", borderColor="#d8ecff",
        font=common.FONT, labelHeight=0.035, flip=False)
    slider.tickLines.opacities = 0
    slider.marker.opacity = 0
    slider_fill = visual.Rect(
        win, width=0, height=SLIDER_SIZE[1],
        pos=(SLIDER_POS[0] - SLIDER_SIZE[0] / 2, SLIDER_POS[1]),
        fillColor="#5a8ec5", lineColor="#5a8ec5")
    lab_left = make_text(win, RATING_ANCHORS[0], pos=(-0.70, -0.17),
                         height=0.045, color="#cccccc")
    lab_mid = make_text(win, RATING_ANCHORS[1], pos=(0, -0.17),
                        height=0.045, color="#cccccc")
    lab_right = make_text(win, RATING_ANCHORS[2], pos=(0.70, -0.17),
                          height=0.045, color="#cccccc")
    value_text = make_text(win, "请拖动滑块进行评分", pos=(0, -0.27),
                           height=0.05, color="#9fd3ff", bold=True)
    recording_title = make_text(win, "正在录音", pos=(0, 0.10), height=0.12,
                                color="#ff8a5a", bold=True)
    recording_info = make_text(win, "", pos=(0, -0.06), height=0.05,
                               color="#cccccc")

    btn_confirm = Button(win, "确认评分", pos=(-0.32, -0.41), size=(0.5, 0.12))
    btn_end = Button(win, "结束", pos=(0.32, -0.41), size=(0.5, 0.12),
                     base_color=COL_BTN_END, hover_color=COL_BTN_END_HOVER)
    btn_stop_recording = Button(win, "停止并保存", pos=(0, -0.34), size=(0.55, 0.13))

    state = STATE_RATING
    count = 1
    pending = None
    running = True

    def reset_rating_ui():
        slider.reset()
        value_text.text = "请拖动滑块进行评分"
        btn_confirm.base_color = COL_BTN
        btn_confirm.hover_color = COL_BTN_HOVER

    def drain_recording():
        """把已采集的音频帧写入当前 WAV 句柄并清空内存缓冲（边录边写）。"""
        frags = mic.recording  # 即 device._recording，poll() 持续往里追加
        if not frags or pending["wav"] is None:
            return
        for clip in frags:
            pending["wav"].write(clip.samples)
            pending["frames"] += clip.samples.shape[0]
        frags.clear()  # 就地清空，避免整段录音常驻内存

    def finalize_recording():
        """停止录音、写完剩余音频并关闭文件，补写 CSV，随后回到评分状态。"""
        nonlocal count, pending, state
        record_end = datetime.datetime.now()
        try:
            if mic.isRecording:
                mic.stop()  # 内部会再 poll 一次，把尾部样本搬入缓冲
        except Exception as err:
            LOGGER.exception("编号 {} 停止录音失败：{}", pending["id"], err)
        try:
            drain_recording()  # 写入尾部样本
        except Exception as err:
            LOGGER.exception("编号 {} 写入音频失败：{}", pending["id"], err)
        try:
            if pending["wav"] is not None:
                pending["wav"].close()
        except Exception as err:
            LOGGER.exception("编号 {} 关闭音频文件失败：{}", pending["id"], err)

        # 无论是否成功获取到音频，VAS-D 评分都必须写入 CSV，避免录音异常导致
        # 评分丢失；无音频时仅清理空文件并把音频相关字段留空/置零。
        if pending["frames"] > 0:
            duration = pending["frames"] / float(sample_rate)
            audio_file = pending["audio_file"]
        else:
            LOGGER.warning("编号 {} 未获取到音频，仅记录评分", pending["id"])
            duration = 0.0
            audio_file = ""
            try:
                os.remove(pending["audio_path"])
                LOGGER.info("已删除空音频文件：{}", pending["audio_path"])
            except OSError as err:
                LOGGER.exception("删除空音频文件失败：{}", err)

        # CSV 写入失败时保持会话存活、不自增 count，便于重录该条目。
        try:
            writer.writerow([
                subject_info["被试编号"], pending["id"], pending["rating"],
                fmt_time(pending["rating_time"]),
                fmt_time(pending["record_start"]), fmt_time(record_end),
                round(duration, 2), audio_file,
            ])
            csv_file.flush()
        except Exception as err:
            LOGGER.exception("编号 {} 写入 CSV 失败：{}", pending["id"], err)
        else:
            LOGGER.info(
                "编号 {} 已保存：rating={}, duration={:.2f}s, audio={}",
                pending["id"], pending["rating"], duration,
                audio_file or "(无)",
            )
            count += 1
        pending = None
        state = STATE_RATING

    def quit_all():
        LOGGER.info("准备退出程序：state={}, pending={}", state, pending is not None)
        # 录音中途退出时，先落盘当前录音与评分，避免数据丢失。
        if state == STATE_RECORDING and pending is not None:
            try:
                finalize_recording()
            except Exception as err:
                LOGGER.exception("退出前保存当前录音失败：{}", err)
        try:
            if mic.isRecording:
                mic.stop()
        except Exception as err:
            LOGGER.exception("停止麦克风失败：{}", err)
        lsl_sender.send_marker("paradigm_end")
        try:
            mic.close()
        except Exception as err:
            LOGGER.exception("关闭麦克风失败：{}", err)
        try:
            csv_file.close()
            LOGGER.info("CSV 文件已关闭")
        except Exception as err:
            LOGGER.exception("关闭 CSV 文件失败：{}", err)
        finally:
            LOGGER.info("程序退出")
            LOGGER.remove()
            win.close()
            core.quit()

    def on_confirm():
        """确认评分：提交当前分值、开始录音，进入录音状态。"""
        nonlocal pending, state
        if state != STATE_RATING:
            return
        rating = slider_live_rating(slider)
        if rating is None:  # 未评分时按钮置灰，这里再兜底一次。
            return
        item_id = f"{count:04d}"
        audio_file = f"{item_id}.wav"
        audio_path = os.path.join(session_dir, audio_file)
        now = datetime.datetime.now()
        pending = {
            "id": item_id,
            "rating": fmt_score(rating),
            "rating_time": now,
            "audio_file": audio_file,
            "audio_path": audio_path,
            "record_start": now,
            "wav": None,
            "frames": 0,
        }
        LOGGER.info("编号 {} 提交评分：rating={}", item_id, pending["rating"])
        lsl_sender.send_score(rating)
        # 打开音频文件并开始录音；任一环节失败都直接收尾，由 finalize_recording
        # 把评分写入 CSV（无音频时音频字段留空），避免评分随录音异常丢失。
        try:
            pending["wav"] = soundfile.SoundFile(
                audio_path, mode="w",
                samplerate=sample_rate, channels=channels)
            mic.record()
        except Exception as err:
            # 设备掉线/被占用等是可预期的运行时错误，记一行即可，无需完整栈。
            LOGGER.error("编号 {} 启动录音失败，仅记录评分：{}", item_id, err)
            finalize_recording()
            reset_rating_ui()
            return
        LOGGER.info("编号 {} 开始录音：audio={}", item_id, audio_file)
        state = STATE_RECORDING
        reset_rating_ui()

    def on_end():
        """结束：退出主循环。"""
        nonlocal running
        LOGGER.info("点击结束按钮")
        running = False

    def on_stop():
        """停止并保存：手动结束当前录音。"""
        if state != STATE_RECORDING or pending is None:
            return
        elapsed = (datetime.datetime.now() - pending["record_start"]).total_seconds()
        LOGGER.info("编号 {} 手动停止录音：elapsed={:.1f}s", pending["id"], elapsed)
        finalize_recording()

    btn_confirm.on_click = on_confirm
    btn_end.on_click = on_end
    btn_stop_recording.on_click = on_stop

    while running:
        if event.getKeys(keyList=["escape"]):
            quit_all()

        if state == STATE_RATING:
            slider.getMouseResponses()
            count_text.text = f"当前编号：{count:04d}"
            # 先派发点击（可能开始录音并重置滑块），再读取分值用于显示，
            # 这样确认后同一帧填充条即归零，无需手动清空 rating。
            dispatcher.dispatch(active=[btn_confirm, btn_end])
            rating = slider_live_rating(slider)

            if rating is None:
                value_text.text = "请拖动滑块进行评分"
                btn_confirm.base_color = "#555555"
                btn_confirm.hover_color = "#555555"
            else:
                value_text.text = f"当前评分：{fmt_score(rating)}"
                btn_confirm.base_color = COL_BTN
                btn_confirm.hover_color = COL_BTN_HOVER

            fill_fraction = rating_fraction(rating)
            slider_fill.width = SLIDER_SIZE[0] * fill_fraction
            slider_fill.pos = (
                SLIDER_POS[0] - SLIDER_SIZE[0] / 2 + slider_fill.width / 2,
                SLIDER_POS[1],
            )

            count_text.draw()
            rate_title.draw()
            slider_fill.draw()
            slider.draw()
            lab_left.draw()
            lab_mid.draw()
            lab_right.draw()
            value_text.draw()
            btn_confirm.draw(mouse)
            btn_end.draw(mouse)
        elif state == STATE_RECORDING:
            # 录音期间需持续 poll，将流缓冲样本搬入录音缓冲，否则超过
            # streamBufferSecs（默认 2s）的音频会被覆盖丢失；随后立即写盘。
            try:
                mic.poll()
                drain_recording()
            except Exception as err:
                # poll/写盘出错也要立即收尾，保住已采集音频与评分。
                # 设备休眠/掉线等是可预期错误，记一行即可，无需完整栈。
                LOGGER.error("编号 {} 录音过程中出错，提前结束并保存：{}",
                             pending["id"], err)
                finalize_recording()
            else:
                now = datetime.datetime.now()
                elapsed = (now - pending["record_start"]).total_seconds()
                recording_info.text = f"编号 {pending['id']}，已录制 {elapsed:.1f} 秒"

                # 到达录音上限自动停止并保存；否则等待手动点击“停止并保存”。
                if elapsed >= MAX_RECORDING_S or mic.isRecBufferFull:
                    reason = "录音时长达到上限" if elapsed >= MAX_RECORDING_S else "录音缓冲已满"
                    LOGGER.info("编号 {} 停止录音：{}, elapsed={:.1f}s",
                                pending["id"], reason, elapsed)
                    finalize_recording()
                else:
                    dispatcher.dispatch(active=[btn_stop_recording])

            recording_title.draw()
            recording_info.draw()
            btn_stop_recording.draw(mouse)

        win.flip()

    quit_all()


if __name__ == "__main__":
    main()
