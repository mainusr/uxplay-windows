import threading
import time
import json
import os
from pathlib import Path

import win32gui
import win32con
import win32api

import pystray
from pystray import Menu, MenuItem
from PIL import Image, ImageDraw


# --------------------------------------------------------
# Persistent config file (stored next to the .exe)
# --------------------------------------------------------

CONFIG_PATH = Path(__file__).with_name("tray_config.json")

DEFAULT_CONFIG = {
    "borderless": False,
    "always_on_top": False
}


def load_config():
    if CONFIG_PATH.exists():
        try:
            return json.loads(CONFIG_PATH.read_text())
        except:
            return DEFAULT_CONFIG.copy()
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2))


config = load_config()


# --------------------------------------------------------
# Window search utilities
# --------------------------------------------------------

def find_uxplay_window():
    """Find the UxPlay window by searching all top-level windows."""
    target_substrings = ["uxplay", "airplay", "receiver"]

    result = []

    def callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd).lower()
            if any(sub in title for sub in target_substrings):
                result.append(hwnd)
        return True

    win32gui.EnumWindows(callback, None)

    return result[0] if result else None


# --------------------------------------------------------
# Window style manipulation
# --------------------------------------------------------

original_styles = {}


def apply_borderless(hwnd):
    style = win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
    original_styles[hwnd] = style
    new_style = style & ~(
        win32con.WS_CAPTION |
        win32con.WS_THICKFRAME |
        win32con.WS_MINIMIZEBOX |
        win32con.WS_MAXIMIZEBOX |
        win32con.WS_SYSMENU
    )
    win32api.SetWindowLong(hwnd, win32con.GWL_STYLE, new_style)
    win32gui.SetWindowPos(
        hwnd, None, 0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
        win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
    )


def remove_borderless(hwnd):
    if hwnd in original_styles:
        win32api.SetWindowLong(hwnd, win32con.GWL_STYLE, original_styles[hwnd])
        win32gui.SetWindowPos(
            hwnd, None, 0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
            win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED
        )


def apply_topmost(hwnd, enable):
    win32gui.SetWindowPos(
        hwnd,
        win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST,
        0, 0, 0, 0,
        win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
    )


# --------------------------------------------------------
# Reapply loop (handles window recreation)
# --------------------------------------------------------

stop_event = threading.Event()


def reapply_loop():
    while not stop_event.is_set():
        hwnd = find_uxplay_window()
        if hwnd:
            if config["borderless"]:
                apply_borderless(hwnd)
            else:
                remove_borderless(hwnd)

            apply_topmost(hwnd, config["always_on_top"])

        time.sleep(1.5)


# --------------------------------------------------------
# Tray icon + menu
# --------------------------------------------------------

def icon_image():
    img = Image.new("RGB", (64, 64), (0, 100, 255))
    d = ImageDraw.Draw(img)
    d.rectangle((18, 22, 46, 42), fill=(255, 255, 255))
    return img


def toggle_borderless(icon, item):
    config["borderless"] = not config["borderless"]
    save_config(config)
    icon.update_menu()


def toggle_topmost(icon, item):
    config["always_on_top"] = not config["always_on_top"]
    save_config(config)
    icon.update_menu()


def quit_app(icon, item):
    stop_event.set()
    icon.stop()


def start_tray():
    menu = Menu(
        MenuItem(
            "Borderless Window",
            toggle_borderless,
            checked=lambda item: config["borderless"]
        ),
        MenuItem(
            "Always on Top",
            toggle_topmost,
            checked=lambda item: config["always_on_top"]
        ),
        MenuItem("Quit", quit_app)
    )

    icon = pystray.Icon("UxPlay", icon_image(), "UxPlay", menu)

    threading.Thread(target=reapply_loop, daemon=True).start()

    icon.run()


if __name__ == "__main__":
    start_tray()
