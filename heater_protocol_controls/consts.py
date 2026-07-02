"""Package-level constants for heater_protocol_controls.

Topic constants live in heater_controller/consts.py — this plugin imports them
(same layering as peripheral_protocol_controls).
"""

PKG = '.'.join(__name__.split('.')[:-1])
PKG_name = PKG.title().replace("_", " ")
