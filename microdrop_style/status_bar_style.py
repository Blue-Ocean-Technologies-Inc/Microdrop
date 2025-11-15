from microdrop_style.helpers import is_dark_mode

DARK_MODE_STYLESHEET = """
QStatusBar {
    color: #dadedf;              
    font-weight: bold;  
    font-size: 14x; 
    font-family: Arial;
    background: #222222;
    border-top: 2px solid #333333 ;
    border-bottom: 2px solid #333333;
}
QStatusBar::item {border: None;}
"""

LIGHT_MODE_STYLESHEET = """
            QStatusBar {
                color: #222222;
                font-weight: bold;
                font-size: 14x;
                font-family: Arial;
                background: #f2f3f4;
                border-top: 2px solid #dadedf;
                border-bottom: 2px solid #dadedf;
            }
            QStatusBar::item {border: None;}
         """

def get_status_bar_stylesheet():
    return DARK_MODE_STYLESHEET if is_dark_mode() else LIGHT_MODE_STYLESHEET