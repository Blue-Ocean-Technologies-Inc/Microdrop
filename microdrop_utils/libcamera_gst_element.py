# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The libcamerasrc element behind a Raspberry Pi CSI camera, reached
through ctypes.

Qt's GStreamer backend builds a ``GstLibcameraSrc`` for a libcamera camera
but hands out no pipeline, and PyGObject is not in the environment. So a
GObject emission hook on GstBin's ``element-added`` signal watches every
bin and keeps a reference to the newest libcamerasrc; its properties are
libcamera's controls (exposure, gain, brightness, ...).

libcamerasrc (libcamera 0.7.2) hands its properties to the camera only as it
starts from NULL: a change while it streams reads back but is never applied
(measured on a Pi 5 with a Camera Module 3, also in a plain GStreamer
pipeline). So property values set here are kept and written onto every new
libcamerasrc as it is created, before it streams; a change takes effect the
next time the camera starts.

Constraints:

- The hook is in place only while a camera is attached
  (capture_new_elements, around the QCamera joining its capture session,
  where Qt creates the element on the calling thread). Left in place, it
  runs Python, so takes the GIL, for every element any GStreamer thread
  adds to any bin, and the app hung at camera start: a streaming thread
  waited for the GIL in the hook while the GUI thread held it, waiting on
  that thread.
- The libraries are loaded after Qt's GStreamer backend (it loads as the
  cameras are listed), before the QCamera exists.
- The environment ships its own GLib, newer than the system one the
  system GStreamer is bound to, and the interpreter's RPATH finds the
  environment's first. Loaded by soname, libgobject (or libgstreamer's
  dependencies, were it loaded here first) would come from the wrong copy
  and fail against the libglib already in the process (undefined
  ``g_string_copy``). So nothing is loaded here: libgstreamer and the
  libgobject it is bound to are opened by the exact paths
  ``/proc/self/maps`` shows Qt's backend mapped, preferring the libgobject
  in libgstreamer's directory when two are. Without ``/proc/self/maps``,
  or before the backend has loaded, the hook is unavailable.
- Strings GStreamer returns are never ``g_free``d: freeing one with
  another GLib copy aborts the process. Nothing here needs to read such a
  string.
"""

# Standard library imports.
import contextlib
import ctypes
import os
import platform
import threading
from ctypes import (
    c_char_p,
    c_double,
    c_float,
    c_int,
    c_size_t,
    c_uint,
    c_ulong,
    c_void_p,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: GType name of the element Qt builds for a libcamera camera.
LIBCAMERA_SRC_TYPE_NAME = b"GstLibcameraSrc"

#: File-name prefixes of libgstreamer and the libgobject it is bound to, as
#: /proc/self/maps lists them (e.g. libgobject-2.0.so.0.8400.4).
GSTREAMER_FILE_PREFIX = "libgstreamer-1.0.so"
GOBJECT_FILE_PREFIX = "libgobject-2.0.so"

#: The process's memory map, one mapped file per line's last field.
PROC_SELF_MAPS = "/proc/self/maps"

#: Qt Multimedia's backend selector; only its GStreamer backend builds a
#: libcamerasrc.
QT_MEDIA_BACKEND_ENV = "QT_MEDIA_BACKEND"
GSTREAMER_MEDIA_BACKEND = "gstreamer"

#: The GstBin signal emitted as an element joins a bin.
ELEMENT_ADDED_SIGNAL = b"element-added"

#: sizeof(GValue) on 64-bit Linux.
GVALUE_SIZE = 24

#: Byte offsets into GParamSpec / GParamSpecEnum on 64-bit Linux.
PARAM_SPEC_VALUE_TYPE_OFFSET = 24
PARAM_SPEC_ENUM_CLASS_OFFSET = 72

#: Fundamental GTypes (G_TYPE_MAKE_FUNDAMENTAL).
G_TYPE_BOOLEAN = 20
G_TYPE_INT = 24
G_TYPE_ENUM = 48
G_TYPE_FLOAT = 56
G_TYPE_DOUBLE = 60

#: GSignalEmissionHook: (ihint, n_param_values, param_values, data) ->
#: keep the hook installed.
_EMISSION_HOOK = ctypes.CFUNCTYPE(c_int, c_void_p, c_uint, c_void_p, c_void_p)


def _mapped_library_paths(file_prefix):
    """Paths of the mapped shared objects whose file name starts with
    ``file_prefix``, in map order; OSError without /proc/self/maps."""
    paths = []

    with open(PROC_SELF_MAPS) as maps:
        for line in maps:
            fields = line.split()

            if len(fields) < 6:
                continue

            path = fields[5]

            if os.path.basename(path).startswith(file_prefix) and path not in paths:
                paths.append(path)

    return paths


def _gstreamer_library_paths():
    """The mapped libgstreamer's path and that of the libgobject it is bound
    to (see the module docstring), or None before Qt's GStreamer backend
    has loaded; OSError without /proc/self/maps."""
    gstreamer_paths = _mapped_library_paths(GSTREAMER_FILE_PREFIX)
    gobject_paths = _mapped_library_paths(GOBJECT_FILE_PREFIX)

    if not gstreamer_paths or not gobject_paths:
        return None

    gstreamer_path = gstreamer_paths[0]
    beside_gstreamer = [
        path
        for path in gobject_paths
        if os.path.dirname(path) == os.path.dirname(gstreamer_path)
    ]
    gobject_path = (beside_gstreamer or gobject_paths)[0]

    if len(gobject_paths) > 1:
        logger.warning(
            f"Several libgobject copies mapped {gobject_paths}; using {gobject_path}"
        )

    return gstreamer_path, gobject_path


def _declare(library, name, restype, *argtypes):
    function = getattr(library, name)
    function.restype = restype
    function.argtypes = list(argtypes)

    return function


class _LibcameraElementHook:
    """The emission hook and the libcamerasrc it last saw."""

    def __init__(self):
        self.attempted = False

        #: The libraries are loaded and the element-added signal found.
        self.ready = False

        #: element-added's signal id, and the hook's id while it is in place.
        self.signal_id = 0
        self.hook_id = 0

        #: Newest libcamerasrc (a held reference), or None.
        self.element = None

        #: Property values set, by name, written onto each new element.
        self.properties = {}

        self.lock = threading.Lock()

        # Kept alive here: GObject calls it for as long as the process runs.
        self.callback = _EMISSION_HOOK(self._on_element_added)

    def load(self):
        if self.attempted:
            return self.ready

        if platform.system() != "Linux":
            self.attempted = True

            return False

        if os.environ.get(QT_MEDIA_BACKEND_ENV) != GSTREAMER_MEDIA_BACKEND:
            self.attempted = True

            return False

        try:
            library_paths = _gstreamer_library_paths()

            # Left for a later call: the backend loads as cameras are listed.
            if library_paths is None:
                logger.info("libcamera image controls wait for GStreamer to load")

                return False

            self.attempted = True
            self._load(*library_paths)
        except (OSError, AttributeError) as error:
            self.attempted = True
            logger.warning(f"libcamera image controls unavailable: {error}")

            return False

        if not self.gst_is_initialized():
            self.gst_init(None, None)

        self.signal_id = self.g_signal_lookup(
            ELEMENT_ADDED_SIGNAL, self.gst_bin_get_type()
        )

        if not self.signal_id:
            logger.warning("libcamera image controls unavailable: no element-added")

            return False

        self.ready = True
        logger.info("libcamerasrc element hook ready")

        return True

    @contextlib.contextmanager
    def capture_new_elements(self):
        if not self.ready:
            yield

            return

        self.hook_id = self.g_signal_add_emission_hook(
            self.signal_id, 0, self.callback, None, None
        )

        try:
            yield
        finally:
            self.g_signal_remove_emission_hook(self.signal_id, self.hook_id)
            self.hook_id = 0

    def _load(self, gstreamer_path, gobject_path):
        # Both already mapped: these return the loaded copies, loading none.
        gstreamer = ctypes.CDLL(gstreamer_path)
        gobject = ctypes.CDLL(gobject_path)
        gtype = c_size_t

        self.gst_is_initialized = _declare(gstreamer, "gst_is_initialized", c_int)
        self.gst_init = _declare(gstreamer, "gst_init", None, c_void_p, c_void_p)
        self.gst_bin_get_type = _declare(gstreamer, "gst_bin_get_type", gtype)

        self.g_signal_lookup = _declare(
            gobject, "g_signal_lookup", c_uint, c_char_p, gtype
        )
        self.g_signal_add_emission_hook = _declare(
            gobject,
            "g_signal_add_emission_hook",
            c_ulong,
            c_uint,
            c_uint,
            _EMISSION_HOOK,
            c_void_p,
            c_void_p,
        )
        self.g_signal_remove_emission_hook = _declare(
            gobject, "g_signal_remove_emission_hook", None, c_uint, c_ulong
        )
        self.g_value_get_object = _declare(
            gobject, "g_value_get_object", c_void_p, c_void_p
        )
        self.g_type_name_from_instance = _declare(
            gobject, "g_type_name_from_instance", c_char_p, c_void_p
        )
        self.g_type_fundamental = _declare(gobject, "g_type_fundamental", gtype, gtype)
        self.g_object_ref = _declare(gobject, "g_object_ref", c_void_p, c_void_p)
        self.g_object_unref = _declare(gobject, "g_object_unref", None, c_void_p)
        self.g_object_class_find_property = _declare(
            gobject, "g_object_class_find_property", c_void_p, c_void_p, c_char_p
        )
        self.g_object_get_property = _declare(
            gobject, "g_object_get_property", None, c_void_p, c_char_p, c_void_p
        )
        self.g_object_set_property = _declare(
            gobject, "g_object_set_property", None, c_void_p, c_char_p, c_void_p
        )
        self.g_value_init = _declare(gobject, "g_value_init", c_void_p, c_void_p, gtype)
        self.g_value_unset = _declare(gobject, "g_value_unset", None, c_void_p)
        self.g_enum_get_value_by_nick = _declare(
            gobject, "g_enum_get_value_by_nick", c_void_p, c_void_p, c_char_p
        )

        self.value_getters = {
            G_TYPE_BOOLEAN: _declare(gobject, "g_value_get_boolean", c_int, c_void_p),
            G_TYPE_INT: _declare(gobject, "g_value_get_int", c_int, c_void_p),
            G_TYPE_ENUM: _declare(gobject, "g_value_get_enum", c_int, c_void_p),
            G_TYPE_FLOAT: _declare(gobject, "g_value_get_float", c_float, c_void_p),
            G_TYPE_DOUBLE: _declare(gobject, "g_value_get_double", c_double, c_void_p),
        }
        self.value_setters = {
            G_TYPE_BOOLEAN: (
                _declare(gobject, "g_value_set_boolean", None, c_void_p, c_int),
                bool,
            ),
            G_TYPE_INT: (
                _declare(gobject, "g_value_set_int", None, c_void_p, c_int),
                round,
            ),
            G_TYPE_ENUM: (
                _declare(gobject, "g_value_set_enum", None, c_void_p, c_int),
                int,
            ),
            G_TYPE_FLOAT: (
                _declare(gobject, "g_value_set_float", None, c_void_p, c_float),
                float,
            ),
            G_TYPE_DOUBLE: (
                _declare(gobject, "g_value_set_double", None, c_void_p, c_double),
                float,
            ),
        }

    def _on_element_added(self, _hint, _n_values, values, _data):
        # Called from C: an exception here would only be printed, so it is
        # logged instead, and the hook stays in place until removed.
        try:
            element = self.g_value_get_object(values + GVALUE_SIZE)

            if element and (
                self.g_type_name_from_instance(element) == LIBCAMERA_SRC_TYPE_NAME
            ):
                self._hold(self.g_object_ref(element))
                self._write_properties()
                logger.info(f"libcamerasrc captured ({len(self.properties)} set)")
        except Exception as error:
            logger.error(f"libcamerasrc element hook failed: {error}")

        return 1

    def _write_properties(self):
        """Write the property values set so far onto the new element."""

        for name, value in list(self.properties.items()):
            try:
                self._write_property(name, value)
            except RuntimeError as error:
                logger.error(f"libcamerasrc {name} not restored: {error}")

    def _hold(self, element):
        """Keep ``element`` (an owned reference) as the newest libcamerasrc,
        dropping the previous one."""

        with self.lock:
            previous = self.element
            self.element = element

        if previous is not None:
            self.g_object_unref(previous)

    def release(self):
        if self.ready:
            self._hold(None)

    # ------------------------------------------------------------------ #
    # Properties                                                           #
    # ------------------------------------------------------------------ #
    def _param_spec(self, name):
        """The element's GParamSpec of property ``name`` and its value
        GType; RuntimeError when there is no element or no such property."""
        element = self.element

        if element is None:
            raise RuntimeError("no libcamerasrc element yet")

        # A GObject instance starts with its class pointer.
        element_class = c_void_p.from_address(element).value
        param_spec = self.g_object_class_find_property(element_class, name.encode())

        if not param_spec:
            raise RuntimeError(f"libcamerasrc has no {name} property")

        value_type = c_size_t.from_address(
            param_spec + PARAM_SPEC_VALUE_TYPE_OFFSET
        ).value

        return element, param_spec, value_type

    def get_property(self, name):
        element, _param_spec, value_type = self._param_spec(name)
        getter = self.value_getters.get(self.g_type_fundamental(value_type))

        if getter is None:
            raise RuntimeError(f"libcamerasrc {name} has an unsupported type")

        value = (ctypes.c_ubyte * GVALUE_SIZE)()
        self.g_value_init(value, value_type)
        self.g_object_get_property(element, name.encode(), value)
        result = getter(value)
        self.g_value_unset(value)

        return result

    def set_property(self, name, value):
        self.properties[name] = value

        if self.element is not None:
            self._write_property(name, value)

    def _write_property(self, name, value):
        element, param_spec, value_type = self._param_spec(name)
        fundamental = self.g_type_fundamental(value_type)

        if fundamental not in self.value_setters:
            raise RuntimeError(f"libcamerasrc {name} has an unsupported type")

        if fundamental == G_TYPE_ENUM and isinstance(value, str):
            value = self._enum_value(name, param_spec, value)

        setter, convert = self.value_setters[fundamental]
        gvalue = (ctypes.c_ubyte * GVALUE_SIZE)()
        self.g_value_init(gvalue, value_type)
        setter(gvalue, convert(value))
        self.g_object_set_property(element, name.encode(), gvalue)
        self.g_value_unset(gvalue)

    def _enum_value(self, name, param_spec, nick):
        enum_class = c_void_p.from_address(
            param_spec + PARAM_SPEC_ENUM_CLASS_OFFSET
        ).value
        enum_value = self.g_enum_get_value_by_nick(enum_class, nick.encode())

        if not enum_value:
            raise RuntimeError(f"libcamerasrc {name} has no {nick!r} value")

        # A GEnumValue starts with its gint value.
        return c_int.from_address(enum_value).value


_hook = _LibcameraElementHook()


def load_libcamera_element_hook():
    """Load what the hook needs; idempotent. Returns whether it is ready:
    never off Linux, nor off Qt's GStreamer backend, and not yet before
    that backend has loaded."""

    return _hook.load()


def is_available():
    """Whether the hook is ready, so libcamerasrc properties can be reached
    once Qt builds the element."""

    return _hook.ready


def capture_new_elements():
    """Context manager: keep a libcamerasrc Qt creates inside it on this
    thread (see the module docstring); a no-op while the hook is not
    ready."""

    return _hook.capture_new_elements()


def has_element():
    return _hook.element is not None


def get_element_property(name):
    """Return libcamerasrc property ``name`` as a bool, int (also enums) or
    float; RuntimeError when it cannot be read."""

    return _hook.get_property(name)


def set_element_property(name, value):
    """Set libcamerasrc property ``name`` on the current element, if any,
    and on every one created after; enums take a nick or an int. It takes
    effect as the camera next starts (see the module docstring).
    RuntimeError when the current element has no such property."""

    _hook.set_property(name, value)


def stored_element_property(name, default=None):
    """The value last set for libcamerasrc property ``name``, else
    ``default``."""

    return _hook.properties.get(name, default)


def release_element():
    """Drop the reference to the newest libcamerasrc."""

    _hook.release()
