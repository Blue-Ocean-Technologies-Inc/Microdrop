
def set_status_bar_message(text: str, window = None, timeout = 2000):
    if window is not None:
        if hasattr(window, "control"):
            window = window.control
        if hasattr(window, "_statusbar"):
            window._statusbar.showMessage(text, timeout = timeout)
        return 
    
    try:
        from pyface.api import GUI

        app = getattr(GUI, "application", None)
        if app and hasattr(app, "windows") and app.windows:
            window = app.windows[0]
            if hasattr(window, "control"):
                window = window.control
            if hasattr(window, "_statusbar"):
                window._statusbar.showMessage(text)
    except Exception:
        pass      