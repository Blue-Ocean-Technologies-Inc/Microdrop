"""Unit tests for PluggableProtocolStateTracker.

No Qt or DockPane required — the tracker accepts a stub object with a
writable ``name`` attribute for title-rewrite tests.
"""

import pytest

from pluggable_protocol_tree.consts import PKG_name
from pluggable_protocol_tree.services.protocol_state_tracker import (
    PluggableProtocolStateTracker,
)


class _NameStub:
    """Stand-in for a DockPane — only ``name`` matters for these tests."""
    def __init__(self):
        self.name = ""


def test_defaults():
    t = PluggableProtocolStateTracker()
    assert t.protocol_name == "untitled"
    assert t.loaded_protocol_path == ""
    assert t.is_modified is False
    assert t.modified_tag == " [modified]"


def test_display_name_clean_dirty_and_untitled():
    t = PluggableProtocolStateTracker()
    assert t.display_name() == f"{PKG_name} - untitled"
    t.protocol_name = "my_assay"
    assert t.display_name() == f"{PKG_name} - my_assay"
    t.is_modified = True
    assert t.display_name() == f"{PKG_name} - my_assay [modified]"


def test_set_loaded_sets_name_path_clears_dirty():
    t = PluggableProtocolStateTracker()
    t.is_modified = True
    t.set_loaded("/tmp/some/path/my_assay.json")
    assert t.protocol_name == "my_assay"
    assert "my_assay.json" in t.loaded_protocol_path
    assert t.is_modified is False


def test_set_saved_sets_name_path_clears_dirty():
    t = PluggableProtocolStateTracker()
    t.is_modified = True
    t.set_saved("/tmp/x/another.json")
    assert t.protocol_name == "another"
    assert t.is_modified is False


def test_set_loaded_rejects_empty_path():
    t = PluggableProtocolStateTracker()
    with pytest.raises(ValueError):
        t.set_loaded("")


def test_reset_returns_defaults():
    t = PluggableProtocolStateTracker()
    t.set_loaded("/tmp/x/foo.json")
    t.is_modified = True
    t.reset()
    assert t.protocol_name == "untitled"
    assert t.loaded_protocol_path == ""
    assert t.is_modified is False


def test_mark_modified_idempotent():
    t = PluggableProtocolStateTracker()
    events = []
    t.observe(lambda e: events.append(e), "is_modified")
    t.mark_modified()
    t.mark_modified()
    t.mark_modified()
    assert len(events) == 1
    assert t.is_modified is True


def test_dock_pane_name_rewritten_on_name_change():
    stub = _NameStub()
    t = PluggableProtocolStateTracker(dock_pane=stub)
    # Initial assignment fires the observer.
    assert stub.name == f"{PKG_name} - untitled"

    t.protocol_name = "demo"
    assert stub.name == f"{PKG_name} - demo"


def test_dock_pane_name_rewritten_on_dirty_change():
    stub = _NameStub()
    t = PluggableProtocolStateTracker(dock_pane=stub)
    t.protocol_name = "demo"
    t.is_modified = True
    assert stub.name == f"{PKG_name} - demo [modified]"
    t.is_modified = False
    assert stub.name == f"{PKG_name} - demo"


def test_no_dock_pane_is_safe():
    """Tracker should be usable headlessly without a dock_pane."""
    t = PluggableProtocolStateTracker()
    t.protocol_name = "demo"      # no crash
    t.is_modified = True          # no crash
    assert t.display_name() == f"{PKG_name} - demo [modified]"
