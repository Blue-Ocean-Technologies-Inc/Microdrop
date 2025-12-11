DARK_MODE_STYLESHEET = """
        QWidget {
            background-color: #2b2b2b;
            color: #ffffff;
            font-family: "Inter", sans-serif; /* Optional global font */
        }
        """

LIGHT_MODE_STYLESHEET = """
        QWidget {
            background-color: #f0f0f0;
            color: #000000;
            font-family: "Inter", sans-serif;
        }
        """

def get_general_style(theme):
    """Defines the base background and text color for the window/container."""
    if theme == "dark":
        return DARK_MODE_STYLESHEET
    else:
        return LIGHT_MODE_STYLESHEET

