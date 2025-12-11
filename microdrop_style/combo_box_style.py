def get_combobox_style(theme):
    """
    Complex styling for QComboBox.
    Note: Styling the drop-down arrow usually requires an image/icon.
    """
    if theme == "dark":
        colors = {
            "bg": "#3a3a3a",
            "border": "#555555",
            "text": "#ffffff",
            "selection": "#4a90e2",
            "hover": "#454545"
        }
    else:
        colors = {
            "bg": "#ffffff",
            "border": "#cccccc",
            "text": "#000000",
            "selection": "#0078d4",
            "hover": "#e6e6e6"
        }

    return f"""
    QComboBox {{
        background-color: {colors['bg']};
        color: {colors['text']};
    }}

    QComboBox:hover {{
        background-color: {colors['hover']};
        border-color: {colors['selection']};
    }}

    /* The drop-down list (popup) */
    QComboBox QAbstractItemView {{
        background-color: {colors['bg']};
        color: {colors['text']};
        selection-background-color: {colors['selection']};
        selection-color: white;
        border: 1px solid {colors['border']};
    }}
    """