"""Thin re-export shim — the protocol preferences moved to
``pluggable_protocol_tree.services.preferences`` (#419 / PPT-14.1).

Kept only so the legacy protocol_grid plugin keeps importing until PPT-9
deletes it. New code must import from the new location."""

from pluggable_protocol_tree.services.preferences import (
    ProtocolPreferences,
    ProtocolPreferencesPane,
    StepTime,
    protocol_grid_tab,
)

__all__ = [
    "ProtocolPreferences",
    "ProtocolPreferencesPane",
    "StepTime",
    "protocol_grid_tab",
]
