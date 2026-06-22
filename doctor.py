# -*- coding: utf-8 -*-
"""
医生端：通过 LSL 控制患者端，并保存患者 VAS-D 评分。
"""

import csv
import datetime
import os
import tomllib

from psychopy import core, event, gui, visual
from pylsl import StreamInfo, StreamInlet, StreamOutlet, resolve_byprop

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, "doctor_config.toml")
SCREEN_INDEX = 0

_DEFAULTS = {
    "screen": {"fullscreen": True, "window_size": [1280, 720]},
    "monitor": {"name": "testMonitor"},
    "lsl": {"command_stream": "estim_bci_command",
            "rating_stream": "estim_bci_rating",
            "resolve_interval_s": 1.0,
            "resolve_timeout_s": 0.05},
    "rating": {"name": "VAS-D",
               "full_name": "visual analog scale-depression"},
    "font": {"name": "Microsoft YaHei"},
}


def load_config():
    cfg = {k: dict(v) for k, v in _DEFAULTS.items()}
    try:
        with open(_CONFIG_PATH, "rb") as f:
            user = tomllib.load(f)
        for section, values in user.items():
            cfg.setdefault(section, {}).update(values)
    except FileNotFoundError:
        print(f"[配置] 未找到 {_CONFIG_PATH}，使用默认显示设置。")
    except Exception as e:
        print(f"[配置] 读取 doctor_config.toml 出错：{e}，使用默认显示设置。")
    return cfg


CFG = load_config()
FULLSCREEN = bool(CFG["screen"]["fullscreen"])
WIN_SIZE = tuple(CFG["screen"]["window_size"])
MONITOR_NAME = str(CFG["monitor"]["name"])
COMMAND_STREAM = str(CFG["lsl"]["command_stream"])
RATING_STREAM = str(CFG["lsl"]["rating_stream"])
RESOLVE_INTERVAL_S = float(CFG["lsl"]["resolve_interval_s"])
RESOLVE_TIMEOUT_S = float(CFG["lsl"]["resolve_timeout_s"])
FONT = str(CFG["font"]["name"])
RATING_NAME = str(CFG["rating"]["name"])
RATING_FULL_NAME = str(CFG["rating"]["full_name"])

DATA_DIR = os.path.join(_BASE_DIR, "data")

COL_BG = "#1e1e28"
COL_BTN = "#3a6ea5"
COL_BTN_HOVER = "#5a8ec5"
COL_BTN_END = "#a53a3a"
COL_BTN_END_HOVER = "#c55a5a"
COL_TEXT = "white"

ST_IDLE = "idle"
ST_STIM = "stimulating"
ST_RATING = "rating"
ST_REVIEW = "review"

MSG_START = "START_STIM"
MSG_END_STIM = "END_STIM"
MSG_END_EXP = "END_EXPERIMENT"
MSG_RATING = "RATING"
MSG_READY = "READY"


def fmt_time(t):
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def make_message(kind, *fields):
    return "|".join([kind, *(str(field) for field in fields)])


def parse_message(message):
    parts = str(message).split("|")
    return parts[0], parts[1:]


def get_screen_size(screen_index):
    try:
        from pyglet import canvas

        screens = canvas.get_display().get_screens()
        if 0 <= screen_index < len(screens):
            return int(screens[screen_index].width), int(screens[screen_index].height)
    except Exception:
        pass
    return WIN_SIZE


def make_window(title, screen_index):
    size = get_screen_size(screen_index) if FULLSCREEN else WIN_SIZE
    return visual.Window(size=size, screen=screen_index, fullscr=FULLSCREEN,
                         color=COL_BG, units="height", allowGUI=True,
                         monitor=MONITOR_NAME, title=title)


def make_outlet(name, source_id):
    info = StreamInfo(name, "Markers", 1, 0, "string", source_id)
    return StreamOutlet(info)


def try_make_inlet(name):
    streams = resolve_byprop("name", name, minimum=1, timeout=RESOLVE_TIMEOUT_S)
    if not streams:
        return None
    return StreamInlet(streams[0], max_buflen=360, recover=True)


def pull_messages(inlet):
    messages = []
    if inlet is None:
        return messages
    while True:
        sample, timestamp = inlet.pull_sample(timeout=0.0)
        if sample is None:
            break
        messages.append((sample[0], timestamp))
    return messages


class Button:
    def __init__(self, win, label, pos, size=(0.5, 0.14),
                 base_color=COL_BTN, hover_color=COL_BTN_HOVER):
        self.base_color = base_color
        self.hover_color = hover_color
        self.rect = visual.Rect(win, width=size[0], height=size[1], pos=pos,
                                fillColor=base_color, lineColor="white",
                                lineWidth=2)
        self.text = visual.TextStim(win, text=label, pos=pos, height=0.05,
                                    font=FONT, color=COL_TEXT, bold=True)

    def contains(self, mouse):
        return self.rect.contains(mouse)

    def draw(self, mouse=None):
        if mouse is not None and self.rect.contains(mouse):
            self.rect.fillColor = self.hover_color
        else:
            self.rect.fillColor = self.base_color
        self.rect.draw()
        self.text.draw()


def make_text(win, text="", pos=(0, 0), height=0.07, color=COL_TEXT, bold=False):
    return visual.TextStim(win, text=text, pos=pos, height=height, font=FONT,
                           color=color, bold=bold, wrapWidth=1.6,
                           alignText="center")


def rising_edge(pressed_now, prev_pressed):
    return pressed_now and not prev_pressed


def fmt_score(score):
    score = float(score)
    return str(int(score)) if score.is_integer() else f"{score:.1f}"


def ask_subject_info():
    info = {"被试编号": "S001", "被试姓名": "", "实验者": ""}
    dlg = gui.DlgFromDict(dictionary=info, title="电刺激范式 - 被试信息",
                          order=["被试编号", "被试姓名", "实验者"])
    if not dlg.OK:
        return None
    return info


def open_data_file(subject_info):
    os.makedirs(DATA_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_path = os.path.join(DATA_DIR, f"{subject_info['被试编号']}_{stamp}.csv")
    csv_file = open(csv_path, "w", newline="", encoding="utf-8-sig")
    writer = csv.writer(csv_file)
    writer.writerow(["被试编号", "被试姓名", "实验者", "轮次", f"{RATING_NAME}评分",
                     "刺激开始时间", "刺激结束时间", "评分提交时间",
                     "评分接收时间", "刺激时长(s)"])
    csv_file.flush()
    return csv_file, writer


def wait_for_patient():
    rating_inlet = None
    last_resolve_t = -RESOLVE_INTERVAL_S
    patient_ready = False

    win = make_window("医生端 - 等待患者端", SCREEN_INDEX)
    win.mouseVisible = False

    title = make_text(win, "等待患者端连接", pos=(0, 0.12),
                      height=0.09, bold=True)
    status = make_text(win, "", pos=(0, -0.04), height=0.05,
                       color="#9fd3ff")
    hint = make_text(win, "请先启动患者端；ESC 可退出", pos=(0, -0.24),
                     height=0.035, color="#888888")
    clock = core.Clock()

    try:
        while not patient_ready:
            if event.getKeys(keyList=["escape"]):
                win.close()
                core.quit()

            now = clock.getTime()
            if rating_inlet is None and now - last_resolve_t >= RESOLVE_INTERVAL_S:
                rating_inlet = try_make_inlet(RATING_STREAM)
                last_resolve_t = now

            for raw_message, _timestamp in pull_messages(rating_inlet):
                kind, _fields = parse_message(raw_message)
                if kind == MSG_READY:
                    patient_ready = True
                    break

            if rating_inlet is None:
                status.text = "状态：正在查找患者端评分流……"
            else:
                status.text = "状态：已发现患者端，等待 READY……"

            title.draw()
            status.draw()
            hint.draw()
            win.flip()
    finally:
        win.close()

    return rating_inlet


def main():
    cmd_outlet = make_outlet(COMMAND_STREAM, "estim_bci_doctor_command")
    rating_inlet = wait_for_patient()

    subject_info = ask_subject_info()
    if subject_info is None:
        cmd_outlet.push_sample([make_message(MSG_END_EXP, 0, fmt_time(datetime.datetime.now()))])
        core.quit()

    csv_file, writer = open_data_file(subject_info)

    win = make_window("医生端", SCREEN_INDEX)
    win.mouseVisible = True
    mouse = event.Mouse(win=win)

    title = make_text(win, "医生端 - 刺激控制", pos=(0, 0.40),
                      height=0.06, bold=True)
    doc_round = make_text(win, "", pos=(0, 0.20), height=0.10, bold=True)
    status = make_text(win, "", pos=(0, 0.02), height=0.05, color="#9fd3ff")
    btn_start = Button(win, "开始刺激", pos=(-0.32, -0.25))
    btn_endstim = Button(win, "结束刺激", pos=(-0.32, -0.25))
    btn_next = Button(win, "进行下一轮", pos=(-0.32, -0.25))
    btn_endexp = Button(win, "结束实验", pos=(0.32, -0.25),
                        base_color=COL_BTN_END, hover_color=COL_BTN_END_HOVER)
    hint = make_text(win, "提示：ESC 可紧急退出", pos=(0, -0.45),
                     height=0.035, color="#888888")

    clock = core.Clock()
    state = ST_IDLE
    rnd = 1
    stim_start_t = None
    stim_end_t = None
    last_rating = None
    last_rating_round = None
    prev_pressed = False
    running = True

    def quit_all():
        try:
            csv_file.close()
        except Exception:
            pass
        win.close()
        core.quit()

    while running:
        if event.getKeys(keyList=["escape"]):
            cmd_outlet.push_sample([make_message(MSG_END_EXP, rnd, fmt_time(datetime.datetime.now()))])
            quit_all()

        for raw_message, _timestamp in pull_messages(rating_inlet):
            kind, fields = parse_message(raw_message)
            if kind == MSG_READY:
                continue
            if kind != MSG_RATING or len(fields) < 3:
                continue
            rating_rnd = int(fields[0])
            rating = float(fields[1])
            submit_time = fields[2]
            if state == ST_RATING and rating_rnd == rnd and stim_start_t and stim_end_t:
                receive_t = datetime.datetime.now()
                duration = (stim_end_t - stim_start_t).total_seconds()
                writer.writerow([
                    subject_info["被试编号"], subject_info["被试姓名"],
                    subject_info["实验者"], rnd, fmt_score(rating),
                    fmt_time(stim_start_t), fmt_time(stim_end_t), submit_time,
                    fmt_time(receive_t), round(duration, 2),
                ])
                csv_file.flush()
                last_rating = rating
                last_rating_round = rating_rnd
                state = ST_REVIEW

        pressed = mouse.getPressed()[0]
        click = rising_edge(pressed, prev_pressed)

        if click and btn_endexp.contains(mouse):
            cmd_outlet.push_sample([make_message(MSG_END_EXP, rnd, fmt_time(datetime.datetime.now()))])
            running = False

        if state == ST_IDLE:
            status.text = "状态：待机，可开始本轮刺激"
            btn_start.base_color = COL_BTN
            btn_start.hover_color = COL_BTN_HOVER
            if click and btn_start.contains(mouse):
                stim_start_t = datetime.datetime.now()
                cmd_outlet.push_sample([make_message(MSG_START, rnd, fmt_time(stim_start_t))])
                state = ST_STIM
        elif state == ST_STIM:
            status.text = "状态：正在刺激……"
            if click and btn_endstim.contains(mouse):
                stim_end_t = datetime.datetime.now()
                cmd_outlet.push_sample([make_message(MSG_END_STIM, rnd, fmt_time(stim_end_t))])
                state = ST_RATING
        elif state == ST_RATING:
            status.text = "状态：等待患者评分回传……"
        elif state == ST_REVIEW:
            status.text = f"第 {last_rating_round} 轮{RATING_NAME}评分：{fmt_score(last_rating)}。是否进行下一轮？"
            if click and btn_next.contains(mouse):
                rnd += 1
                stim_start_t = None
                stim_end_t = None
                last_rating = None
                last_rating_round = None
                state = ST_IDLE

        doc_round.text = f"当前刺激轮数：第 {rnd} 轮"
        title.draw()
        doc_round.draw()
        status.draw()
        if state == ST_IDLE:
            btn_start.draw(mouse)
        elif state == ST_STIM:
            btn_endstim.draw(mouse)
        elif state == ST_REVIEW:
            btn_next.draw(mouse)
        btn_endexp.draw(mouse)
        hint.draw()
        win.flip()

        prev_pressed = pressed

    quit_all()


if __name__ == "__main__":
    main()
