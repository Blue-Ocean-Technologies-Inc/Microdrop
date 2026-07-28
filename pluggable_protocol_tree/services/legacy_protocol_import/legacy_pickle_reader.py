"""Read protocols authored in the Python 2 MicroDrop.

A legacy protocol file is an extension-less pickle (protocol 2) of
``microdrop.protocol.Protocol``. Reading one in Python 3 needs three
accommodations, all handled by ``_LegacyUnpickler``:

* ``encoding="latin1"`` so Python 2 ``str`` payloads decode.
* The ``microdrop.*`` classes are long gone, so they resolve to a stub
  type. ``Protocol`` arrives via the OBJ opcode (which calls ``cls()``)
  and ``Step`` via NEWOBJ (``cls.__new__(cls)``), so the stub tolerates
  both construction paths.
* pandas 2.x deleted ``Int64Index`` and friends. Without remapping them
  to ``pandas.Index`` the ``drop_routes`` DataFrames raise
  ``ModuleNotFoundError`` and route data vanishes silently.

``Step.plugin_data`` values are themselves pickled blobs, so this module
unpickles them eagerly -- callers only ever see plain dicts.
"""

import io
import pickle

import pandas as pd

from logger.logger_service import get_logger

from .consts import (
    LEGACY_PROBE_ALLOWED_MODULE_PREFIXES, LEGACY_STUBBED_MODULE_PREFIXES,
    REMOVED_PANDAS_INDEX_CLASSES, REMOVED_PANDAS_INDEX_MODULE,
    SUPPORTED_LEGACY_PROTOCOL_VERSION,
)

logger = get_logger(__name__)


class _LegacyObjectStub:
    """Stand-in for any long-gone MicroDrop class met while unpickling.

    Accepts both construction paths pickle uses and copies the instance
    state straight onto ``__dict__`` so attributes read naturally."""

    def __init__(self, *args, **kwargs):
        pass

    def __setstate__(self, state):
        if isinstance(state, dict):
            self.__dict__.update(state)
        else:
            self.__dict__["state"] = state


class _LegacyUnpickler(pickle.Unpickler):
    def find_class(self, module, name):
        if module.startswith(LEGACY_STUBBED_MODULE_PREFIXES):
            return type(name, (_LegacyObjectStub,), {"__module__": module})
        if (module == REMOVED_PANDAS_INDEX_MODULE
                and name in REMOVED_PANDAS_INDEX_CLASSES):
            return pd.Index
        return super().find_class(module, name)


class _ProbeUnpickler(_LegacyUnpickler):
    """Strict unpickler used only to *probe* whether a file looks like a
    legacy protocol (``is_legacy_protocol_file``).

    The directory scanner calls that probe on every file it finds in a
    ``protocols/`` folder, not just the one the user picked -- so unlike
    ``_LegacyUnpickler`` (used to actually read the chosen file), this one
    must not defer arbitrary modules to the real ``find_class``, which
    would import and construct whatever class an unrelated file names,
    running its ``__reduce__``/``__setstate__`` merely to populate a
    dropdown."""

    def find_class(self, module, name):
        if (module.startswith(LEGACY_STUBBED_MODULE_PREFIXES)
                or module.startswith(LEGACY_PROBE_ALLOWED_MODULE_PREFIXES)):
            return super().find_class(module, name)
        raise pickle.UnpicklingError(
            f"probe unpickler refuses module {module!r} outside the "
            f"legacy/pandas/numpy/builtins allowlist")


def _loads(blob) -> object:
    """Unpickle a nested per-plugin blob. Latin-1 round-trips the bytes that
    came in as a Python 2 ``str``."""
    raw = blob.encode("latin1") if isinstance(blob, str) else blob
    return _LegacyUnpickler(io.BytesIO(raw), encoding="latin1").load()


class LegacyStep:
    """One step of a legacy protocol: legacy plugin name -> its value dict."""

    def __init__(self, plugin_data: dict):
        self.plugin_data = plugin_data


class LegacyProtocol:
    """A legacy protocol: a flat list of steps (the format has no groups)."""

    def __init__(self, name: str, version: str, n_repeats: int,
                 steps: list):
        self.name = name
        self.version = version
        self.n_repeats = n_repeats
        self.steps = steps


def _read_raw_protocol(path: str, unpickler_cls=_LegacyUnpickler):
    with open(path, "rb") as handle:
        return unpickler_cls(handle, encoding="latin1").load()


def read_legacy_protocol(path: str) -> LegacyProtocol:
    """Read ``path`` into a ``LegacyProtocol`` with every nested plugin blob
    already unpickled. Raises if the file is not a legacy protocol."""
    raw = _read_raw_protocol(path)
    version = str(getattr(raw, "version", "") or "")
    if version and version != SUPPORTED_LEGACY_PROTOCOL_VERSION:
        logger.warning(
            f"{path!r}: legacy protocol version {version!r} differs from "
            f"the version this importer was built against "
            f"({SUPPORTED_LEGACY_PROTOCOL_VERSION!r}); conversion may be "
            f"incomplete or incorrect.")
    steps = []
    for index, raw_step in enumerate(getattr(raw, "steps", [])):
        plugin_data = {}
        for plugin_name, blob in getattr(raw_step, "plugin_data", {}).items():
            try:
                values = _loads(blob)
            except Exception as e:
                logger.warning(
                    f"step {index} of {path!r}: could not unpickle "
                    f"{plugin_name!r} data: {e}", exc_info=True)
                continue
            if isinstance(values, dict):
                plugin_data[plugin_name] = values
            else:
                logger.debug(
                    f"step {index} of {path!r}: {plugin_name!r} data is "
                    f"{type(values).__name__}, not a dict; ignored")
        steps.append(LegacyStep(plugin_data))
    return LegacyProtocol(
        name=str(getattr(raw, "name", "") or ""),
        version=version,
        n_repeats=int(getattr(raw, "n_repeats", 1) or 1),
        steps=steps,
    )


def is_legacy_protocol_file(path: str) -> bool:
    """True when ``path`` unpickles into something that looks like a legacy
    protocol. Used to filter directory listings, which in practice contain
    unrelated files (a 7-Zip archive sits in one real protocols folder).

    Uses ``_ProbeUnpickler``, not the full ``_LegacyUnpickler``: the
    directory scanner runs this over *every* file in a ``protocols/``
    folder just to populate a dropdown, so it must not resolve/construct
    arbitrary classes from files the user never chose."""
    try:
        raw = _read_raw_protocol(path, unpickler_cls=_ProbeUnpickler)
    except Exception as e:
        logger.debug(f"{path!r} is not a legacy protocol: {e}")
        return False
    return isinstance(getattr(raw, "steps", None), list)
