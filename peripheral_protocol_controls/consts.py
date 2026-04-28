"""Package-level constants for peripheral_protocol_controls.

Topic constants live in peripheral_controller/consts.py — this plugin
imports them. See PPT-5 spec section 2 for the layering reasoning.
"""

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")
