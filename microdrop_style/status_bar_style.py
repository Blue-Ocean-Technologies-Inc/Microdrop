# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

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

def get_status_bar_stylesheet(theme):
    if theme == 'dark':
        return DARK_MODE_STYLESHEET
    else:
        return LIGHT_MODE_STYLESHEET