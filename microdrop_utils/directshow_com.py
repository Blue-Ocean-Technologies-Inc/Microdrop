# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The DirectShow COM interfaces the camera-control fallbacks need, declared
for comtypes (Windows only).

Only the methods used are declared, but every method before them in an
interface's vtable is too, since COM dispatches by slot. Import this module
lazily: comtypes exists only on Windows.
"""

# Standard library imports.
from ctypes import POINTER, c_long, c_ulong, c_void_p

# Third-party imports.
from comtypes import COMMETHOD, GUID, HRESULT, IPersist, IUnknown

#: The system device enumerator, and the video capture device category.
CLSID_SYSTEM_DEVICE_ENUM = GUID("{62BE5D10-60EB-11d0-BD3B-00A0C911CE86}")
CLSID_VIDEO_INPUT_DEVICE_CATEGORY = GUID("{860BB310-5D01-11d0-BD3B-00A0C911CE86}")

#: CameraControlProperty and CameraControlFlags values (strmif.h); exposure
#: is in log2 seconds.
CAMERA_CONTROL_EXPOSURE = 4
CAMERA_CONTROL_FOCUS = 6
CAMERA_CONTROL_FLAGS_AUTO = 0x1
CAMERA_CONTROL_FLAGS_MANUAL = 0x2

#: VideoProcAmpProperty values (strmif.h) by v4l2 control name; its flags
#: share CameraControlFlags' values.
VIDEO_PROC_AMP_PROPERTIES = {
    "brightness": 0,
    "contrast": 1,
    "hue": 2,
    "saturation": 3,
    "sharpness": 4,
    "gamma": 5,
    "white_balance_temperature": 7,
    "backlight_compensation": 8,
    "gain": 9,
}


class IPersistStream(IPersist):
    _iid_ = GUID("{00000109-0000-0000-C000-000000000046}")

    # Vtable slots only; never called.
    _methods_ = [
        COMMETHOD([], HRESULT, name)
        for name in ("IsDirty", "Load", "Save", "GetSizeMax")
    ]


class IMoniker(IPersistStream):
    _iid_ = GUID("{0000000f-0000-0000-C000-000000000046}")

    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            name,
            (["in"], c_void_p, "pbc"),
            (["in"], c_void_p, "pmkToLeft"),
            (["in"], POINTER(GUID), "riid"),
            (["out"], POINTER(POINTER(IUnknown)), "ppv"),
        )
        for name in ("BindToObject", "BindToStorage")
    ]


class IEnumMoniker(IUnknown):
    _iid_ = GUID("{00000102-0000-0000-C000-000000000046}")

    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "Next",
            (["in"], c_ulong, "celt"),
            (["out"], POINTER(POINTER(IMoniker)), "rgelt"),
            (["out"], POINTER(c_ulong), "pceltFetched"),
        ),
    ]


class ICreateDevEnum(IUnknown):
    _iid_ = GUID("{29840822-5B84-11D0-BD3B-00A0C911CE86}")

    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "CreateClassEnumerator",
            (["in"], POINTER(GUID), "clsidDeviceClass"),
            (["out"], POINTER(POINTER(IEnumMoniker)), "ppEnumMoniker"),
            (["in"], c_ulong, "dwFlags"),
        ),
    ]


class IAMCameraControl(IUnknown):
    _iid_ = GUID("{C6E13370-30AC-11d0-A18C-00A0C9118956}")

    _methods_ = [
        COMMETHOD(
            [],
            HRESULT,
            "GetRange",
            (["in"], c_long, "Property"),
            (["out"], POINTER(c_long), "pMin"),
            (["out"], POINTER(c_long), "pMax"),
            (["out"], POINTER(c_long), "pSteppingDelta"),
            (["out"], POINTER(c_long), "pDefault"),
            (["out"], POINTER(c_long), "pCapsFlags"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "Set",
            (["in"], c_long, "Property"),
            (["in"], c_long, "lValue"),
            (["in"], c_long, "Flags"),
        ),
        COMMETHOD(
            [],
            HRESULT,
            "Get",
            (["in"], c_long, "Property"),
            (["out"], POINTER(c_long), "lValue"),
            (["out"], POINTER(c_long), "Flags"),
        ),
    ]


class IAMVideoProcAmp(IUnknown):
    _iid_ = GUID("{C6E13360-30AC-11d0-A18C-00A0C9118956}")

    # Same layout as IAMCameraControl, over VideoProcAmpProperty values.
    _methods_ = IAMCameraControl._methods_
