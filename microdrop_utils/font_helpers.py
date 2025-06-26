from pathlib import Path
from PySide6.QtGui import QFontDatabase

def load_font_family(font_path):
    if Path(font_path).exists():
        id_ = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(id_)
        if families:            
            return families[0]
    return None