# tray.py
# UxPlay Windows tray controller with toggles for:
#  - Borderless window (hide title bar / chrome)
#  - Always on top (pin)
#
# Tailored to find the UxPlay window titled "Direct3D11 renderer"

from pathlib import Path
import threading
import time
import json
import traceback

# optional robust process scanning
try:
    import psutil
except Exception:
    psutil = None

# win32
try:
    import win32gui
    import win32con
    import win32api
    import win32process
except Exception:
    print("Missing pywin32. Install with: pip install pywin32")
    raise

# tray
try:
    import pystray
    from pystray import MenuItem, Menu
    from PIL import Image, ImageDraw
except Exception:
    print("Missing pystray / pillow. Install with: pip install pystray pillow")
    raise

# -----------------------
# Configuration / state
# -----------------------

HERE = Path(__file__).resolve().parent
CONFIG_FILE = HERE / "tray_config.json"

DEFAULT_CFG = {
    "borderless": False,
    "always_on_top": False,
    "title_substrings": ["Direct3D11 renderer"]
}

def load_config():
    try:
        if CONFIG_FILE.exists():
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception:
        traceback.print_exc()
    cfg = DEFAULT_CFG.copy()
    save_config(cfg)
    return cfg

def save_config(cfg):
    try:
        CONFIG_FILE.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    except Exception:
        traceback.print_exc()

cfg = load_config()

# -----------------------
# Window detection
# -----------------------

def enum_visible_windows():
    result = []
    def cb(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            title = win32gui.GetWindowText(hwnd)
            if title:
                result.append((hwnd, title))
        return True
    win32gui.EnumWindows(cb, None)
    return result

def find_uxplay_windows():
    substrs = [s.lower() for s in cfg.get("title_substrings", []) if s]
    matches = []

    for hwnd, title in enum_visible_windows():
        tl = title.lower()
        if any(sub in tl for sub in substrs):
            matches.append(hwnd)

    if not matches and psutil:
        try:
            for proc in psutil.process_iter(['pid', 'name']):
                name = (proc.info.get('name') or '').lower()
                if name in ("uxplay", "uxplay.exe"):
                    pid = proc.info['pid']
                    acc = []
                    def cb(hwnd, arr):
                        _, wnd_pid = win32process.GetWindowThreadProcessId(hwnd)
                        if wnd_pid == pid and win32gui.IsWindowVisible(hwnd):
                            arr.append(hwnd)
                        return True
                    win32gui.EnumWindows(cb, acc)
                    for h in acc:
                        if win32gui.GetWindowText(h):
                            matches.append(h)
        except Exception:
            traceback.print_exc()

    return list(dict.fromkeys(matches))

# -----------------------
# Style manipulation
# -----------------------

_original_styles = {}

def _get_style(hwnd):
    try:
        return win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
    except Exception:
        try:
            return win32api.GetWindowLong(hwnd, win32con.GWL_STYLE)
        except Exception:
            return None

def _set_style(hwnd, style):
    try:
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
    except Exception:
        try:
            win32api.SetWindowLong(hwnd, win32con.GWL_STYLE, style)
        except Exception:
            raise

    try:
        win32gui.SetWindowPos(
            hwnd,
            None,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE |
            win32con.SWP_NOSIZE |
            win32con.SWP_NOZORDER |
            win32con.SWP_FRAMECHANGED
        )
    except Exception:
        pass

def make_borderless(hwnd):
    try:
        style = _get_style(hwnd)
        if style is None:
            return
        if hwnd not in _original_styles:
            _original_styles[hwnd] = style
        new_style = style & ~(win32con.WS_CAPTION |
                              win32con.WS_THICKFRAME |
                              win32con.WS_MINIMIZEBOX |
                              win32con.WS_MAXIMIZEBOX |
                              win32con.WS_SYSMENU)
        _set_style(hwnd, new_style)
    except Exception:
        traceback.print_exc()

def restore_style(hwnd):
    try:
        orig = _original_styles.get(hwnd)
        if orig is not None:
            _set_style(hwnd, orig)
            del _original_styles[hwnd]
    except Exception:
        traceback.print_exc()

def set_topmost(hwnd, enable=True):
    try:
        win32gui.SetWindowPos(
            hwnd,
            win32con.HWND_TOPMOST if enable else win32con.HWND_NOTOPMOST,
            0, 0, 0, 0,
            win32con.SWP_NOMOVE | win32con.SWP_NOSIZE
        )
    except Exception:
        traceback.print_exc()

# -----------------------
# Reapply loop
# -----------------------

_stop_event = threading.Event()
_REAPPLY_INTERVAL = 1.5

def apply_settings_once():
    hwnds = find_uxplay_windows()
    if not hwnds:
        return
    for h in hwnds:
        try:
            if cfg.get("borderless"):
                make_borderless(h)
            else:
                restore_style(h)
            set_topmost(h, cfg.get("always_on_top", False))
        except Exception:
            traceback.print_exc()

def reapply_loop():
    while not _stop_event.is_set():
        try:
            apply_settings_once()
        except Exception:
            traceback.print_exc()
        _stop_event.wait(_REAPPLY_INTERVAL)

# -----------------------
# Tray UI
# -----------------------

def _create_image():
    size = (64, 64)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((6, 6, 58, 58), 10, fill=(20, 120, 200, 255))
    d.polygon([(26, 20), (26, 44), (46, 32)], fill=(255, 255, 255, 255))
    return img

def on_toggle_borderless(icon, item):
    cfg["borderless"] = not cfg.get("borderless", False)
    save_config(cfg)
    apply_settings_once()
    icon.update_menu()

def on_toggle_topmost(icon, item):
    cfg["always_on_top"] = not cfg.get("always_on_top", False)
    save_config(cfg)
    apply_settings_once()
    icon.update_menu()

def on_reapply_now(icon, item):
    apply_settings_once()

def on_quit(icon, item):
    _stop_event.set()
    try:
        icon.visible = False
    except Exception:
        pass
    icon.stop()

def build_menu():
    return (
        MenuItem(
            "Borderless window (hide title bar)",
            on_toggle_borderless,
            checked=lambda item: cfg.get("borderless", False)
        ),
        MenuItem(
            "Always on Top",
            on_toggle_topmost,
            checked=lambda item: cfg.get("always_on_top", False)
        ),
        Menu.SEPARATOR,
        MenuItem("Reapply now", on_reapply_now),
        MenuItem("Quit", on_quit),
    )

def start_tray():
    icon = pystray.Icon("uxplay", _create_image(), "UxPlay", Menu(*build_menu()))
    t = threading.Thread(target=reapply_loop, daemon=True)
    t.start()
    try:
        icon.run()
    finally:
        _stop_event.set()
        t.join(timeout=1.0)

if __name__ == "__main__":
    print("Tray loaded. Looking for UxPlay window titled:", cfg.get("title_substrings"))
    start_tray()
