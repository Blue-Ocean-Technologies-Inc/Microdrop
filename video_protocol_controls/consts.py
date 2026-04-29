"""Package-level constants for video_protocol_controls.

Topic constants live in device_viewer/consts.py — this plugin
imports them. See PPT-6 spec section 2 for the layering reasoning.
"""

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")
