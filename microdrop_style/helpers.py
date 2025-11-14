import os
import sys


def is_dark_mode():
    if sys.platform == "darwin":
        import subprocess
        try:
            mode = subprocess.check_output(
                "defaults read -g AppleInterfaceStyle",
                shell=True
            ).strip()
            return mode == b"Dark"
        except Exception:
            return False
    elif sys.platform.startswith("win"):
        try:
            import winreg
            reg = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(
                reg,
                r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            )
            apps_use_light_theme, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return apps_use_light_theme == 0
        except Exception:
            return False
    else:
        gtk_theme = os.environ.get("GTK_THEME", "").lower()
        if "dark" in gtk_theme:
            return True
        qt_theme = os.environ.get("QT_QPA_PLATFORMTHEME", "").lower()
        if "dark" in qt_theme:
            return True
        # KDE check
        kde_globals = os.path.expanduser("~/.config/kdeglobals")
        if os.path.isfile(kde_globals):
            try:
                with open(kde_globals, "r") as f:
                    if "ColorScheme=Dark" in f.read():
                        return True
            except Exception:
                pass
        return False
