from qfluentwidgets import InfoBar, InfoBarPosition

def show_message(parent, level, title, content, duration=None):
    defaults = {
        "info":    {"duration": 3000, "fn": InfoBar.info},
        "error":   {"duration": 5000, "fn": InfoBar.error},
        "success": {"duration": 3000, "fn": InfoBar.success},
        "warning": {"duration": 4000, "fn": InfoBar.warning},
    }
    cfg = defaults[level]
    d = duration if duration is not None else cfg["duration"]
    cfg["fn"](title, content, duration=d, position=InfoBarPosition.TOP_RIGHT, parent=parent)
