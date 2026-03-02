"""
Discover OpenDrop serial port by VID:PID or use an explicit port hint.
"""

import re
from typing import Optional

from serial.tools import list_ports

from .consts import OPENDROP_VID_PID


def find_opendrop_port(port_hint: Optional[str] = None) -> Optional[str]:
    """
    Return the OpenDrop serial port device name.

    - If port_hint is non-empty, use it (with simple prefix glob if *).
    - Else return first port whose hwid matches OPENDROP_VID_PID.
    - If none found, return None.
    """
    hint = (port_hint or "").strip()
    if hint:
        if "*" in hint:
            prefix = hint.replace("*", "")
            for p in list_ports.comports():
                if p.device.startswith(prefix) or prefix in p.device:
                    return p.device
            return None
        return hint

    # Match VID:PID (e.g. 239A:800B) in port hwid
    pattern = re.compile(re.escape(OPENDROP_VID_PID), re.IGNORECASE)
    for p in list_ports.comports():
        if p.hwid and pattern.search(p.hwid):
            return p.device
    return None
