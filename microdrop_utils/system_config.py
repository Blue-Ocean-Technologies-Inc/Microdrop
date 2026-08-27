# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

import platform

# Private global variable (hidden from outside)
_IS_RASPBERRY_PI = False
_INITIALIZED = False

def detect_rpi():
    """
    Auto-detects if we are on a Raspberry Pi using the platform string.
    Returns True/False.
    """
    plat_str = platform.platform().lower()
    is_linux = 'linux' in plat_str
    is_arm64 = 'aarch64' in plat_str
    is_rpi_kernel = 'rpi' in plat_str or 'rpt' in plat_str

    return is_linux and is_arm64 and is_rpi_kernel

def set_rpi_mode():
    """
    Sets the rpi mode flag.
    """
    global _IS_RASPBERRY_PI, _INITIALIZED

    _IS_RASPBERRY_PI = detect_rpi()
    _INITIALIZED = True

    return _IS_RASPBERRY_PI

def is_rpi():
    """
    Accessor: Returns the global Raspberry Pi state.
    """
    # Auto-init if the user forgot to call set_rpi_mode()
    if not _INITIALIZED:
        set_rpi_mode()

    return _IS_RASPBERRY_PI