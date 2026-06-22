# -*- coding: utf-8 -*-
"""
患者端：接收医生端 LSL 指令，显示刺激状态并回传 VAS 评分。
"""

import datetime
import os
import tomllib

from psychopy import core, event, visual
from pylsl import StreamInfo, StreamInlet, StreamOutlet, resolve_byprop

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_CONFIG_PATH = os.path.join(_BASE_DIR, "patient_config.toml")

_DEFAULTS = {
    "screen": {"patient": 0, "fullscreen": True, "window_size": [1280, 720]},
    "monitor": {"name": "testMonitor"},
    "lsl": {"command_stream": "estim_bci_command",
            "rating_stream": "estim_bci_rating",
            "resolve_interval_s": 1.0,
            "resolve_timeout_s": 0.05},
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
        print(f"[配置] 读取 patient_config.toml 出错：{e}，使用默认显示设置。")
    return cfg


CFG = load_config()
PATIENT_SCREEN = int(CFG["screen"]["patient"])
FULLSCREEN = bool(CFG["screen"]["fullscreen"])
WIN_SIZE = tuple(CFG["screen"]["window_size"])
MONITOR_NAME = str(CFG["monitor"]["name"])
COMMAND_STREAM = str(CFG["lsl"]["command_stream"])
RATING_STREAM = str(CFG["lsl"]["rating_stream"])
RESOLVE_INTERVAL_S = float(CFG["lsl"]["resolve_interval_s"])
RESOLVE_TIMEOUT_S = float(CFG["lsl"]["resolve_timeout_s"])
FONT = str(CFG["font"]["name"])

VAS_MIN, VAS_MAX = 0, 100

COL_BG = "#1e1e28"
COL_BTN = "#3a6ea5"
COL_BTN_HOVER = "#5a8ec5"
COL_TEXT = "white"

ST_IDLE = "idle"
ST_STIM = "stimulating"
ST_RATING = "rating"

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


def main():
    rating_outlet = make_outlet(RATING_STREAM, "estim_bci_patient_rating")
    command_inlet = None
    last_resolve_t = -RESOLVE_INTERVAL_S

    win = make_window("患者端", PATIENT_SCREEN)
    win.mouseVisible = True
    mouse = event.Mouse(win=win)

    pat_wait = make_text(win, "请稍候，等待医生开始……", pos=(0, 0),
                         height=0.09, bold=True)
    pat_connecting = make_text(win, "正在连接医生端……", pos=(0, -0.16),
                               height=0.045, color="#9fd3ff")
    pat_stim = make_text(win, "正在刺激", pos=(0, 0.05), height=0.16,
                         color="#ff8a5a", bold=True)
    pat_stim_sub = make_text(win, "请保持放松", pos=(0, -0.18),
                             height=0.06, color="#cccccc")
    pat_rate_title = make_text(win, "请对刚才的疼痛程度进行评分",
                               pos=(0, 0.34), height=0.07, bold=True)
    pat_slider = visual.Slider(
        win, ticks=(VAS_MIN, VAS_MAX), labels=None,
        pos=(0, 0.0), size=(1.2, 0.06), granularity=1, style="slider",
        color="white", fillColor="#5a8ec5", borderColor="white",
        font=FONT, labelHeight=0.04, flip=False)
    pat_lab_left = make_text(win, "0\n无痛", pos=(-0.62, -0.12),
                             height=0.045)
    pat_lab_right = make_text(win, "100\n最痛", pos=(0.62, -0.12),
                              height=0.045)
    pat_value = make_text(win, "", pos=(0, 0.16), height=0.08,
                          color="#9fd3ff", bold=True)
    btn_confirm = Button(win, "确认评分", pos=(0, -0.34), size=(0.5, 0.14))

    clock = core.Clock()
    state = ST_IDLE
    current_rnd = 1
    last_ready_t = -RESOLVE_INTERVAL_S
    prev_pressed = False
    running = True

    def reset_rating_ui():
        pat_slider.reset()
        pat_value.text = ""
        btn_confirm.base_color = COL_BTN
        btn_confirm.hover_color = COL_BTN_HOVER

    def quit_all():
        win.close()
        core.quit()

    while command_inlet is None:
        if event.getKeys(keyList=["escape"]):
            quit_all()

        now = clock.getTime()
        if now - last_resolve_t >= RESOLVE_INTERVAL_S:
            command_inlet = try_make_inlet(COMMAND_STREAM)
            last_resolve_t = now

        pat_connecting.draw()
        win.flip()

    while running:
        if event.getKeys(keyList=["escape"]):
            quit_all()

        now = clock.getTime()
        if state == ST_IDLE and now - last_ready_t >= RESOLVE_INTERVAL_S:
            rating_outlet.push_sample([
                make_message(MSG_READY, current_rnd, fmt_time(datetime.datetime.now()))
            ])
            last_ready_t = now

        for raw_message, _timestamp in pull_messages(command_inlet):
            kind, fields = parse_message(raw_message)
            if kind == MSG_START and fields:
                current_rnd = int(fields[0])
                state = ST_STIM
            elif kind == MSG_END_STIM and fields:
                current_rnd = int(fields[0])
                reset_rating_ui()
                state = ST_RATING
            elif kind == MSG_END_EXP:
                running = False

        pressed = mouse.getPressed()[0]
        click = rising_edge(pressed, prev_pressed)

        if state == ST_RATING:
            rating = pat_slider.getRating()
            if rating is None:
                pat_value.text = "请拖动滑块进行评分"
                btn_confirm.base_color = "#555555"
                btn_confirm.hover_color = "#555555"
            else:
                pat_value.text = f"当前评分：{int(rating)}"
                btn_confirm.base_color = COL_BTN
                btn_confirm.hover_color = COL_BTN_HOVER

            if click and btn_confirm.contains(mouse) and rating is not None:
                submit_t = datetime.datetime.now()
                rating_outlet.push_sample([
                    make_message(MSG_RATING, current_rnd, int(rating), fmt_time(submit_t))
                ])
                current_rnd += 1
                reset_rating_ui()
                state = ST_IDLE

        if state == ST_IDLE:
            pat_wait.draw()
        elif state == ST_STIM:
            pat_stim.draw()
            pat_stim_sub.draw()
        elif state == ST_RATING:
            pat_rate_title.draw()
            pat_slider.draw()
            pat_lab_left.draw()
            pat_lab_right.draw()
            pat_value.draw()
            btn_confirm.draw(mouse)
        win.flip()

        prev_pressed = pressed

    quit_all()


if __name__ == "__main__":
    main()
