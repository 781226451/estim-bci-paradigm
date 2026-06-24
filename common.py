# -*- coding: utf-8 -*-
"""患者端共用：配置加载与界面组件。"""

import os
import tomllib

from psychopy import visual

_BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SCREEN_INDEX = 0

COL_BG = "#1e1e28"
COL_BTN = "#3a6ea5"
COL_BTN_HOVER = "#5a8ec5"
COL_BTN_END = "#a53a3a"
COL_BTN_END_HOVER = "#c55a5a"
COL_TEXT = "white"

BASE_DEFAULTS = {
    "screen": {"fullscreen": True, "window_size": [1280, 720]},
    "monitor": {"name": "testMonitor"},
    "rating": {"name": "VAS-D",
               "full_name": "visual analog scale-depression"},
    "font": {"name": "Microsoft YaHei"},
}

# 由 init_config 填充，供下方界面函数读取。
FULLSCREEN = True
WIN_SIZE = (1280, 720)
MONITOR_NAME = "testMonitor"
FONT = "Microsoft YaHei"
RATING_NAME = "VAS-D"
RATING_FULL_NAME = "visual analog scale-depression"


def load_config(config_path, defaults):
    cfg = {k: dict(v) for k, v in defaults.items()}
    try:
        with open(config_path, "rb") as f:
            user = tomllib.load(f)
        for section, values in user.items():
            cfg.setdefault(section, {}).update(values)
    except FileNotFoundError:
        print(f"[配置] 未找到 {config_path}，使用默认显示设置。")
    except Exception as e:
        print(f"[配置] 读取 {os.path.basename(config_path)} 出错：{e}，使用默认显示设置。")
    return cfg


def init_config(config_name, extra_defaults=None):
    """加载配置并填充模块级运行参数，返回完整配置字典。"""
    defaults = {k: dict(v) for k, v in BASE_DEFAULTS.items()}
    for section, values in (extra_defaults or {}).items():
        defaults.setdefault(section, {}).update(values)

    cfg = load_config(os.path.join(_BASE_DIR, config_name), defaults)

    global FULLSCREEN, WIN_SIZE, MONITOR_NAME, FONT, RATING_NAME, RATING_FULL_NAME
    FULLSCREEN = bool(cfg["screen"]["fullscreen"])
    WIN_SIZE = tuple(cfg["screen"]["window_size"])
    MONITOR_NAME = str(cfg["monitor"]["name"])
    FONT = str(cfg["font"]["name"])
    RATING_NAME = str(cfg["rating"]["name"])
    RATING_FULL_NAME = str(cfg["rating"]["full_name"])
    return cfg


def fmt_time(t):
    return t.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]


def fmt_score(score):
    score = float(score)
    return str(int(score)) if score.is_integer() else f"{score:.1f}"


def rising_edge(pressed_now, prev_pressed):
    return pressed_now and not prev_pressed


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


def make_text(win, text="", pos=(0, 0), height=0.07, color=COL_TEXT, bold=False):
    return visual.TextStim(win, text=text, pos=pos, height=height, font=FONT,
                           color=color, bold=bold, wrapWidth=1.6,
                           alignText="center")


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
