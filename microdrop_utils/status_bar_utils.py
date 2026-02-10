from pyface.api import GUI

def get_status_bar(window=None):
    if window is not None:
        if hasattr(window, "control"):
            window = window.control
        if hasattr(window, "_statusbar"):
            return window._statusbar
        return None
    
    try:
        app = getattr(GUI, "application", None)
        if app and hasattr(app, "windows") and app.windows:
            window = app.windows[0]
            if hasattr(window, "control"):
                window = window.control
            if hasattr(window, "_statusbar"):
                return window._statusbar
    except Exception:
        return None

def set_status_bar_message(text: str, window=None, timeout=3000):
    statusbar = get_status_bar(window)
    if statusbar:
        statusbar.showMessage(text, timeout=timeout)

def clear_status_bar_message(window=None):
    statusbar = get_status_bar(window)
    if statusbar:
        statusbar.clearMessage()