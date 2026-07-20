"""Tests for pyface_wrapper.choose() — the multi-choice dialog (issue #542).

choose() blocks in dialog.exec(), so every interactive test monkeypatches
BaseMessageDialog.exec to simulate the user's click (button actions call
close_with_result -> done(code), which sets the result without an event
loop) and then returns dialog.result() exactly as a real exec() would.
"""

import pytest

from microdrop_application.dialogs.base_message_dialog import BaseMessageDialog
from microdrop_application.dialogs.pyface_wrapper import _map_choice, choose

FOUR = ["Append", "Replace", "New step", "Duplicate"]


def _press(label, captured=None):
    def fake_exec(self):
        if captured is not None:
            captured["dialog"] = self
        self.get_button(label).click()
        return self.result()
    return fake_exec


def _dismiss():
    def fake_exec(self):
        self.reject()   # what Escape / the window-close X do
        return self.result()
    return fake_exec


# --- result mapping -------------------------------------------------------

def test_map_choice_returns_label_for_custom_codes():
    assert _map_choice(BaseMessageDialog.RESULT_CUSTOM_1, FOUR) == "Append"
    assert _map_choice(BaseMessageDialog.RESULT_CUSTOM_1 + 3, FOUR) == "Duplicate"


def test_map_choice_cancel_and_out_of_range_are_none():
    assert _map_choice(BaseMessageDialog.RESULT_CANCEL, FOUR) is None
    assert _map_choice(BaseMessageDialog.RESULT_OK, FOUR) is None
    assert _map_choice(BaseMessageDialog.RESULT_CUSTOM_1 + len(FOUR), FOUR) is None


# --- interactive paths ----------------------------------------------------

def test_choose_returns_clicked_label(qapp, monkeypatch):
    monkeypatch.setattr(BaseMessageDialog, "exec", _press("Replace"))
    assert choose(None, "Attach chain?", choices=FOUR) == "Replace"


def test_choose_fourth_choice_beyond_named_custom_codes(qapp, monkeypatch):
    """RESULT_CUSTOM_* names stop at 3; the mechanism must not."""
    monkeypatch.setattr(BaseMessageDialog, "exec", _press("Duplicate"))
    assert choose(None, "msg", choices=FOUR) == "Duplicate"


def test_choose_cancel_button_returns_none(qapp, monkeypatch):
    monkeypatch.setattr(BaseMessageDialog, "exec", _press("Cancel"))
    assert choose(None, "msg", choices=FOUR) is None


def test_choose_escape_returns_none(qapp, monkeypatch):
    monkeypatch.setattr(BaseMessageDialog, "exec", _dismiss())
    assert choose(None, "msg", choices=FOUR) is None


def test_choose_buttons_present_and_cancel_styled_as_exit(qapp, monkeypatch):
    captured = {}
    monkeypatch.setattr(BaseMessageDialog, "exec", _press("Append", captured))
    choose(None, "msg", choices=FOUR)
    dialog = captured["dialog"]
    assert set(dialog.buttons) == set(FOUR) | {"Cancel"}
    assert dialog.get_button("Cancel").objectName() == "exitButton"
    assert dialog.get_button("Append").objectName() != "exitButton"


def test_choose_without_cancel_button(qapp, monkeypatch):
    captured = {}
    monkeypatch.setattr(BaseMessageDialog, "exec", _press("Append", captured))
    choose(None, "msg", choices=FOUR, cancel=False)
    assert "Cancel" not in captured["dialog"].buttons


def test_choose_checkbox_convention(qapp, monkeypatch):
    """checkbox_text upgrades the return to (label, checked), matching
    the other wrapper functions."""
    monkeypatch.setattr(BaseMessageDialog, "exec", _press("Append"))
    result = choose(None, "msg", choices=FOUR, checkbox_text="Don't ask again")
    assert result == ("Append", False)


# --- input validation -----------------------------------------------------

def test_choose_rejects_empty_choices(qapp):
    with pytest.raises(ValueError):
        choose(None, "msg", choices=[])


def test_choose_rejects_duplicate_choices(qapp):
    with pytest.raises(ValueError):
        choose(None, "msg", choices=["A", "A"])


def test_choose_rejects_cancel_label_collision(qapp):
    with pytest.raises(ValueError):
        choose(None, "msg", choices=["A", "Cancel"])
