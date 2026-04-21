"""Package-level constants for the pluggable protocol tree.

Follows the MicroDrop convention: PKG derived from __name__, topic constants
defined here, ACTOR_TOPIC_DICT aggregating the listener→topic map."""

import os

PKG = ".".join(__name__.split(".")[:-1])
PKG_name = PKG.title().replace("_", " ")

current_folder_path = os.path.dirname(os.path.abspath(__file__))

# Envisage extension point id (registered in plugin.py)
PROTOCOL_COLUMNS = f"{PKG}.protocol_columns"

# Clipboard MIME type for copy/cut/paste of protocol rows
PROTOCOL_ROWS_MIME = "application/x-microdrop-rows+json"

# Persistence schema version
PERSISTENCE_SCHEMA_VERSION = 1

# Topic constants (no executor topics yet — added in PPT-2)
# Reserved namespace for future use:
PROTOCOL_TOPIC_PREFIX = "microdrop/pluggable_protocol_tree"

# No ACTOR_TOPIC_DICT entries yet — no listener in PPT-1.
ACTOR_TOPIC_DICT: dict[str, list[str]] = {}
