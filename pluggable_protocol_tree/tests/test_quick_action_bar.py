"""QuickActionBar is a pure rendering widget: it takes a list of
IQuickAction instances and produces one QToolButton per action,
ordered by (priority, action_id). It has no state and no Qt-signal
connections — the controller (next task) attaches click handlers."""

from pluggable_protocol_tree.models.quick_action import BaseQuickAction
from pluggable_protocol_tree.views.quick_action_bar import QuickActionBar


def _make(action_id, *, priority=50, icon="add", tip="t", shortcut=""):
    return BaseQuickAction(action_id=action_id, icon_text=icon,
                           tooltip=tip, priority=priority,
                           shortcut=shortcut)


def test_bar_renders_one_button_per_action(qapp):
    bar = QuickActionBar(actions=[
        _make("a"), _make("b"), _make("c"),
    ])
    assert len(bar.buttons) == 3
    assert set(bar.buttons.keys()) == {"a", "b", "c"}


def test_bar_orders_by_priority_then_action_id(qapp):
    bar = QuickActionBar(actions=[
        _make("z", priority=10),
        _make("a", priority=20),
        _make("c", priority=10),
    ])
    assert list(bar.buttons.keys()) == ["c", "z", "a"]


def test_button_text_is_icon_text_and_tooltip_matches(qapp):
    bar = QuickActionBar(actions=[
        _make("add_step", icon="add", tip="Add step below selection"),
    ])
    b = bar.buttons["add_step"]
    assert b.text() == "add"
    assert b.toolTip() == "Add step below selection"


def test_bar_skips_duplicate_action_id_and_logs_warning(qapp, caplog):
    """Two contributions with the same action_id is a programming bug
    in the contributing plugins. The bar logs a warning and keeps the
    first one (priority-sorted); the duplicate is dropped from both
    self.buttons AND the visible layout."""
    bar = QuickActionBar(actions=[
        _make("add_step", priority=10),
        _make("add_step", priority=20),
    ])
    assert list(bar.buttons.keys()) == ["add_step"]
    assert "add_step" in caplog.text
