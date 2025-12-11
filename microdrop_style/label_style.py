DARK_MODE_STYLESHEET = """
        QLabel {
            color: #e0e0e0;
        }
        /* Example: Create a specific class for headers if needed */
        QLabel[class="header"] {
            color: #ffffff;
        }
        """

LIGHT_MODE_STYLESHEET = """
        QLabel {
            color: #333333;
        }
        QLabel[class="header"] {
            color: #000000;
        }
        """

def get_label_style(theme):
    """Specific overrides for QLabels (headers, etc)."""
    if theme == "dark":
        return DARK_MODE_STYLESHEET
    else:
        return LIGHT_MODE_STYLESHEET