"""Package-level constants for dropbot_protocol_controls.

Topic constants live in dropbot_controller/consts.py — this plugin
imports them. See PPT-4 spec section 3, "Topic ownership rationale"
for the layering reasoning.
"""

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")
