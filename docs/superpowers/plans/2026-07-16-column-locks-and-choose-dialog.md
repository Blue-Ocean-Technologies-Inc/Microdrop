# Per-Row Column Locks (#541) + Multi-Choice Dialog (#542) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement Microdrop issue #542 (a `choose()` multi-choice dialog in `pyface_wrapper`) and issue #541 (generic owner-keyed per-row column locks in `pluggable_protocol_tree`), the two blockers for fluorescence-microdrop-plugin-py#6.

**Architecture:** #542 adds one thin wrapper function reusing `BaseMessageDialog`'s existing arbitrary-buttons map and `RESULT_CUSTOM_*` codes — no new dialog machinery. #541 adds owner-keyed lock storage on `BaseRow` (`{col_id: {owner: reason}}`), enforces it centrally in `MvcTreeModel.flags()` (clearing `ItemIsEditable | ItemIsUserCheckable`), surfaces reasons as tooltips, auto-wires repaint in `_wire_row_observers`, and pays two debts: `repeat_duration_controls` adopts the mechanism (Route Reps genuinely goes read-only) and `CaptureAtComboBoxView` gets its missing repaint dependency.

**Tech Stack:** Python 3.13 (pixi env), Traits/HasTraits, PySide6 via `pyface.qt`, pytest (+ `QT_QPA_PLATFORM=offscreen`).

**Design sources:** GitHub issues Blue-Ocean-Technologies-Inc/Microdrop#541 and #542; design doc `fluorescence-microdrop-plugin-py/docs/superpowers/specs/2026-07-16-fluorescence-capture-chain-design.md` (status: approved).

## Global Constraints

- **Working copy:** the Microdrop submodule at `C:\Users\Info\PycharmProjects\pixi-microdrop\microdrop-py\src`. All file paths below are relative to it. Do NOT work in the standalone clone at `~/PycharmProjects/Microdrop` (it is mid-work on an unrelated bugfix branch).
- **Branching:** never commit to `main`. `git fetch origin` first. Task 1 happens on branch `feat/542-choose-dialog`; Tasks 2–6 on branch `feat/541-per-row-column-locks`; both branched from `origin/main` (`22ebd63c` or later). One PR per issue.
- **Commits:** Conventional Commits (`type(scope): subject`, imperative, ~50 chars; why/what bodies). CI enforces the format. Commit steps in this plan mean: **verify, report to the user, and WAIT for their explicit approval before running `git commit`** (stored user preference — never chain a commit behind a verification command).
- **Test runs:** stored user preference says no unprompted pytest. At execution start, ask the user ONCE whether the new/changed test files may be run headlessly during this plan. If yes, "Run" steps use: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/<file> -q` (never bare `python` — must go through `pixi run`; never the full suite). If no, hand each command to the user and wait.
- **Code style:** f-strings only (no `%s`/`.format()`); no raw `QMessageBox`/`pyface.api` dialogs — everything through `microdrop_application.dialogs.pyface_wrapper`; never alias constants to new names; match surrounding comment density.
- **Locks are never persisted.** `services/persistence.py::_collect_row_flags` and the `row_flags` map stay untouched.
- `fluorescence-microdrop-plugin-py/` inside the submodule tree is a separate nested repo — never stage files from it in Microdrop commits.

---

## Part A — issue #542 (branch `feat/542-choose-dialog`)

### Task 1: `choose()` in pyface_wrapper

**Files:**
- Modify: `microdrop_application/dialogs/pyface_wrapper.py` (after `confirm()`, ~line 186; plus imports and `__all__`)
- Create: `microdrop_application/tests/__init__.py`
- Create: `microdrop_application/tests/conftest.py`
- Test: `microdrop_application/tests/test_pyface_wrapper_choose.py`

**Interfaces:**
- Consumes: `BaseMessageDialog` (`buttons` map, `RESULT_CUSTOM_1 = 10`, `RESULT_CANCEL = 0`, `close_with_result`, `_button_sort_key` role sorting), `_prepare_dialog`, `_with_checkbox` — all already in the file.
- Produces: `choose(parent, message, title, choices, cancel, cancel_label, detail, detail_visible_lines, informative, text_format, **kwargs) -> Optional[str]` — returns the clicked choice label, or `None` when no choice was made (Cancel button, Escape, window close). With `checkbox_text` in kwargs, returns `(label_or_None, checked)`. Also `_map_choice(result: int, choices) -> Optional[str]` (module-private, unit-tested). The fluorescence attach dialog (#6) will call `choose(..., choices=["Append", "Replace", "New step"])`.

**Design points settled (from the issue):** return the caller's own choice label, not an int — no one has to remember which `RESULT_CUSTOM_*` meant what, and the range extends past 3 for free (`RESULT_CUSTOM_1 + i` for choice *i*; `done()` takes any int, the named constants are just the first three). Escape/close map to `None`, distinct from every real choice. `parent`/`title`/checkbox conventions match the sibling functions.

- [ ] **Step 1: Branch**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src"
git fetch origin
git switch -c feat/542-choose-dialog origin/main
```

- [ ] **Step 2: Create the test package**

`microdrop_application/tests/__init__.py` — empty file.

`microdrop_application/tests/conftest.py`:

```python
"""Shared fixtures for microdrop_application tests."""

import pytest


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication so Qt dialog tests can construct
    widgets without crashing (mirrors pluggable_protocol_tree's)."""
    from pyface.qt.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
    # Don't quit — lets subsequent test modules reuse the QApplication.
```

- [ ] **Step 3: Write the failing tests**

`microdrop_application/tests/test_pyface_wrapper_choose.py`:

```python
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
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/microdrop_application/tests/test_pyface_wrapper_choose.py -q`
Expected: FAIL — `ImportError: cannot import name '_map_choice'`.

- [ ] **Step 5: Implement `choose()`**

In `microdrop_application/dialogs/pyface_wrapper.py`:

1. Change the typing import (line 22) to `from typing import Optional, Sequence`.
2. Insert after `confirm()` (after line 185):

```python
def _map_choice(result: int, choices) -> Optional[str]:
    """Map a dialog result code back to the caller's choice label.

    Choice *i* closes with ``RESULT_CUSTOM_1 + i``. Anything else —
    the Cancel button's RESULT_CANCEL, Escape, the window-close X —
    is "no choice made" and maps to None.
    """
    offset = result - BaseMessageDialog.RESULT_CUSTOM_1
    if 0 <= offset < len(choices):
        return list(choices)[offset]
    return None


def choose(
    parent: Optional[QWidget] = None,
    message: str = "",
    title: str = "Select an Option",
    choices: Sequence[str] = (),
    cancel: bool = True,
    cancel_label: str = "Cancel",
    detail: Optional[str] = None,
    detail_visible_lines: Optional[int] = None,
    informative: Optional[str] = None,
    text_format: Optional[str] = None,
    **kwargs,
):
    """Styled multi-choice question dialog (issue #542).

    Shows one button per entry in *choices* (kept in order, primary
    styling) plus an optional *cancel_label* button (secondary "exit"
    styling, sorted leftmost by the dialog). Returns the clicked choice
    label, or None when no choice was made — the Cancel button, Escape,
    and the window-close X all mean None.

    Reuses BaseMessageDialog's arbitrary ``buttons`` map and the
    RESULT_CUSTOM_* range (choice i closes with RESULT_CUSTOM_1 + i, so
    more than three choices work — the named constants are just the
    first three codes).

    If *checkbox_text* is provided (via kwargs), a checkbox is added and
    the return value becomes a ``(label_or_None, checked)`` tuple, the
    same convention as the other wrapper functions.
    """
    choices = list(choices)
    if not choices:
        raise ValueError("choose() needs at least one choice")
    if len(set(choices)) != len(choices):
        raise ValueError(f"choose() choices must be unique, got {choices}")
    if cancel and cancel_label in choices:
        raise ValueError(
            f"cancel_label {cancel_label!r} collides with a choice")

    dialog_ref = [None]  # mutable closure reference, as in confirm()

    def close_result(result):
        if dialog_ref[0] is not None:
            dialog_ref[0].close_with_result(result)

    buttons = {}
    if cancel:
        buttons[cancel_label] = {
            "action": lambda: close_result(BaseMessageDialog.RESULT_CANCEL),
            "role": "exit",
        }
    for i, label in enumerate(choices):
        code = BaseMessageDialog.RESULT_CUSTOM_1 + i
        buttons[label] = {"action": lambda code=code: close_result(code)}

    def create_dialog(**opts):
        return BaseMessageDialog(
            dialog_type=BaseMessageDialog.TYPE_QUESTION,
            buttons=buttons, **opts,
        )

    dialog = _prepare_dialog(create_dialog, parent, title, message, detail,
                             detail_visible_lines, informative, text_format,
                             **kwargs)
    dialog_ref[0] = dialog

    result = dialog.exec()
    return _with_checkbox(dialog, _map_choice(result, choices))
```

3. Add `"choose",` to `__all__` (after `"confirm",`).

- [ ] **Step 6: Run tests to verify they pass**

Run: same command as Step 4.
Expected: all PASS.

- [ ] **Step 7: Commit (after user approval), push, PR**

```bash
git add microdrop_application/dialogs/pyface_wrapper.py microdrop_application/tests/
git commit -m "feat(microdrop_application): add choose() multi-choice dialog

pyface_wrapper had no way to ask a question with more than three
outcomes: confirm() maps everything down to YES/NO/CANCEL. choose()
exposes BaseMessageDialog's existing arbitrary-buttons map through the
wrapper, returning the clicked choice label (None on cancel/dismiss)
so callers never juggle RESULT_CUSTOM_* codes.

Closes #542"
git push -u origin feat/542-choose-dialog
gh pr create --repo Blue-Ocean-Technologies-Inc/Microdrop \
  --title "feat(microdrop_application): add choose() multi-choice dialog" \
  --body "..."   # summarize as in the commit; reference #542 and the fluorescence#6 dependency
```

---

## Part B — issue #541 (branch `feat/541-per-row-column-locks`)

### Task 2: Owner-keyed lock storage on BaseRow

**Files:**
- Modify: `pluggable_protocol_tree/models/row.py` (BaseRow, ~line 20-51)
- Test: `pluggable_protocol_tree/tests/test_row.py` (append)

**Interfaces:**
- Produces (used by Tasks 3–5 and by the fluorescence plugin later):
  - `BaseRow.column_locks: Dict(Str, Dict)` — `{col_id: {owner: reason}}`, reassigned wholesale on every change so trait observers fire.
  - `BaseRow.lock_column(col_id: str, owner: str, reason: str = "") -> None`
  - `BaseRow.unlock_column(col_id: str, owner: str) -> None` — releases only that owner's lock; unknown ids/owners are a no-op.
  - `BaseRow.is_column_locked(col_id: str) -> bool` — True while ANY owner holds a lock.
  - `BaseRow.column_lock_reasons(col_id: str) -> list[str]` — non-empty reasons, for the tooltip.

- [ ] **Step 1: Branch**

```bash
cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py/src"
git switch -c feat/541-per-row-column-locks origin/main
```

- [ ] **Step 2: Write the failing tests**

Append to `pluggable_protocol_tree/tests/test_row.py`:

```python
# --- per-row column locks (issue #541) ---

def test_lock_column_makes_column_locked():
    r = BaseRow()
    assert r.is_column_locked("capture") is False
    r.lock_column("capture", owner="fluorescence", reason="Chain 'GFP' owns this step")
    assert r.is_column_locked("capture") is True


def test_unlock_requires_all_owners_released():
    """Owner-keying is the point: one releasing owner must not re-enable
    a cell another owner still wants locked."""
    r = BaseRow()
    r.lock_column("capture", owner="fluorescence", reason="chain")
    r.lock_column("capture", owner="other_plugin", reason="busy")
    r.unlock_column("capture", owner="fluorescence")
    assert r.is_column_locked("capture") is True
    r.unlock_column("capture", owner="other_plugin")
    assert r.is_column_locked("capture") is False


def test_unlock_unknown_owner_or_column_is_noop():
    r = BaseRow()
    r.unlock_column("capture", owner="nobody")          # never locked
    r.lock_column("capture", owner="fluorescence")
    r.unlock_column("capture", owner="somebody_else")   # wrong owner
    assert r.is_column_locked("capture") is True


def test_column_lock_reasons_collects_nonempty_reasons():
    r = BaseRow()
    r.lock_column("capture", owner="fluorescence", reason="Chain 'GFP' owns this step")
    r.lock_column("capture", owner="other_plugin")      # no reason given
    assert r.column_lock_reasons("capture") == ["Chain 'GFP' owns this step"]
    assert r.column_lock_reasons("voltage") == []


def test_relock_same_owner_updates_reason():
    r = BaseRow()
    r.lock_column("capture", owner="fluorescence", reason="old")
    r.lock_column("capture", owner="fluorescence", reason="new")
    assert r.column_lock_reasons("capture") == ["new"]


def test_lock_and_unlock_fire_trait_notifications():
    """The tree model repaints by observing column_locks — mutations
    must reassign the dict so the notification actually fires."""
    r = BaseRow()
    events = []
    r.observe(lambda e: events.append(e), "column_locks")
    r.lock_column("capture", owner="fluorescence")
    assert len(events) == 1
    r.unlock_column("capture", owner="fluorescence")
    assert len(events) == 2


def test_locks_do_not_leak_between_rows():
    a, b = BaseRow(), BaseRow()
    a.lock_column("capture", owner="fluorescence")
    assert b.is_column_locked("capture") is False
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_row.py -q`
Expected: new tests FAIL with `AttributeError: ... object has no attribute 'lock_column'`; pre-existing tests still pass.

- [ ] **Step 4: Implement lock storage on BaseRow**

In `pluggable_protocol_tree/models/row.py`:

1. Extend the traits import (line 14):

```python
from traits.api import (
    HasTraits, Str, List, Instance, Tuple, Property, Bool, Dict, provides,
)
```

2. Inside `BaseRow`, after the `repeat_duration_controls` trait (line 31), add the trait; after `dotted_path()` (line 51), add the methods:

```python
    column_locks = Dict(
        Str, Dict,
        desc="Owner-keyed per-row column locks: {col_id: {owner: reason}}. "
             "Runtime-derived state, rebuilt from its source on load — "
             "never persisted (a lock with no live owner could never be "
             "released).")
```

```python
    # --- per-row column locks (issue #541) ---

    def lock_column(self, col_id: str, owner: str, reason: str = "") -> None:
        """Lock ``col_id``'s cell on this row on behalf of ``owner``.

        ``reason`` surfaces as the cell tooltip. The whole dict is
        rebuilt and reassigned so trait observers (the tree model's
        repaint wiring) fire — Traits does not notify on nested
        mutation.
        """
        locks = {cid: dict(owners) for cid, owners in self.column_locks.items()}
        locks.setdefault(col_id, {})[owner] = reason
        self.column_locks = locks

    def unlock_column(self, col_id: str, owner: str) -> None:
        """Release ``owner``'s lock on ``col_id``. The cell stays locked
        while any other owner still holds one. Unknown column ids or
        owners are a no-op."""
        if owner not in self.column_locks.get(col_id, {}):
            return
        locks = {cid: dict(owners) for cid, owners in self.column_locks.items()}
        del locks[col_id][owner]
        if not locks[col_id]:
            del locks[col_id]
        self.column_locks = locks

    def is_column_locked(self, col_id: str) -> bool:
        return bool(self.column_locks.get(col_id))

    def column_lock_reasons(self, col_id: str) -> list:
        """Non-empty lock reasons for ``col_id`` — the cell tooltip."""
        return [reason for reason in self.column_locks.get(col_id, {}).values()
                if reason]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: same command as Step 3. Expected: all PASS.

- [ ] **Step 6: Commit (after user approval)**

```bash
git add pluggable_protocol_tree/models/row.py pluggable_protocol_tree/tests/test_row.py
git commit -m "feat(pluggable_protocol_tree): owner-keyed column locks on BaseRow

One column disabling another column's cell on a given row had no
mechanism (issue #541). Store {col_id: {owner: reason}} on the row:
a column releases only its own lock and the cell stays locked while
any owner holds one, so two gating plugins can't fight. Mutations
reassign the dict wholesale so trait observers fire.

Part of #541"
```

### Task 3: Central enforcement + tooltip + auto-wired repaint in MvcTreeModel

**Files:**
- Modify: `pluggable_protocol_tree/views/qt_tree_model.py` (`flags()` line 168-172, `data()` lines 128-134, `_wire_row_observers` line 286-326, new `_on_row_locks_changed`)
- Test: `pluggable_protocol_tree/tests/test_column_locks.py` (new)

**Interfaces:**
- Consumes: Task 2's `is_column_locked` / `column_lock_reasons` / `column_locks` trait.
- Produces: `MvcTreeModel.flags()` clears `Qt.ItemIsEditable | Qt.ItemIsUserCheckable` on locked cells; `data(ToolTipRole)` returns the joined reasons; every row's `column_locks` is observed automatically (no `depends_on_row_traits` declaration needed by gated columns) emitting a whole-row `dataChanged`; the grey read-only fill and BulkSetDialog's flag checks now see lock-aware flags.

- [ ] **Step 1: Write the failing tests**

Create `pluggable_protocol_tree/tests/test_column_locks.py`:

```python
"""MvcTreeModel enforcement of per-row column locks (issue #541).

Locks live on the row (see test_row.py for storage semantics); this
module covers the central enforcement: flags() clearing, tooltip,
grey read-only fill, and the auto-wired repaint."""

from pyface.qt.QtCore import Qt
from traits.api import Bool

from pluggable_protocol_tree.builtins.name_column import make_name_column
from pluggable_protocol_tree.builtins.type_column import make_type_column
from pluggable_protocol_tree.models.column import BaseColumnModel, Column
from pluggable_protocol_tree.models.row_manager import RowManager
from pluggable_protocol_tree.views.columns.checkbox import CheckboxColumnView
from pluggable_protocol_tree.views.qt_tree_model import MvcTreeModel


class _BoolColumnModel(BaseColumnModel):
    def trait_for_row(self):
        return Bool(False)


def _make_checkbox_column():
    return Column(
        model=_BoolColumnModel(col_id="capture", col_name="Capture",
                               default_value=False),
        view=CheckboxColumnView(),
    )


def _build():
    manager = RowManager(columns=[
        make_type_column(), make_name_column(), _make_checkbox_column(),
    ])
    manager.add_step()
    qm = MvcTreeModel(manager)
    ids = [c.model.col_id for c in manager.columns]
    return manager, qm, ids


def _cell(qm, row_idx, col_idx):
    from pyface.qt.QtCore import QModelIndex
    return qm.index(row_idx, col_idx, QModelIndex())


def test_locked_editable_cell_loses_editable_flag():
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("name"))
    assert qm.flags(idx) & Qt.ItemIsEditable
    row.lock_column("name", owner="test", reason="because")
    assert not (qm.flags(idx) & Qt.ItemIsEditable)


def test_locked_checkbox_cell_loses_user_checkable_flag():
    """Checkboxes are never ItemIsEditable — clearing only that flag
    would do nothing at all. Both flags must go."""
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("capture"))
    assert qm.flags(idx) & Qt.ItemIsUserCheckable
    row.lock_column("capture", owner="fluorescence", reason="chain owns step")
    flags = qm.flags(idx)
    assert not (flags & Qt.ItemIsUserCheckable)
    assert not (flags & Qt.ItemIsEditable)
    assert flags & Qt.ItemIsEnabled    # still selectable/enabled, just inert


def test_unlocking_last_owner_restores_flags():
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("capture"))
    row.lock_column("capture", owner="a")
    row.lock_column("capture", owner="b")
    row.unlock_column("capture", owner="a")
    assert not (qm.flags(idx) & Qt.ItemIsUserCheckable)   # b still holds
    row.unlock_column("capture", owner="b")
    assert qm.flags(idx) & Qt.ItemIsUserCheckable


def test_lock_reason_is_cell_tooltip():
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("capture"))
    assert qm.data(idx, Qt.ToolTipRole) is None
    row.lock_column("capture", owner="fluorescence",
                    reason="Captured by fluorescence chain")
    assert qm.data(idx, Qt.ToolTipRole) == "Captured by fluorescence chain"


def test_locked_cell_gets_read_only_background():
    """The grey fill tests for the absence of BOTH flags — it must read
    lock-aware flags, not the view's raw get_flags."""
    manager, qm, ids = _build()
    row = manager.root.children[0]
    idx = _cell(qm, 0, ids.index("name"))
    assert qm.data(idx, Qt.BackgroundRole) is None
    row.lock_column("name", owner="test")
    assert qm.data(idx, Qt.BackgroundRole) is not None


def test_lock_change_emits_datachanged_for_the_row():
    """Repaint is auto-wired: no gated column declares anything."""
    manager, qm, ids = _build()
    row = manager.root.children[0]
    received = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append(
            (top.row(), top.column(), bottom.column())),
    )
    row.lock_column("capture", owner="fluorescence")
    assert (0, 0, len(ids) - 1) in received
    received.clear()
    row.unlock_column("capture", owner="fluorescence")
    assert (0, 0, len(ids) - 1) in received


def test_lock_repaint_wired_for_rows_added_after_model_creation():
    manager, qm, ids = _build()
    manager.add_step()
    received = []
    qm.dataChanged.connect(
        lambda top, bottom, *_: received.append((top.row(), top.column())),
    )
    manager.root.children[1].lock_column("capture", owner="fluorescence")
    assert (1, 0) in received
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_column_locks.py -q`
Expected: FAIL — locked cells keep their flags, tooltip is None, no dataChanged.

- [ ] **Step 3: Implement enforcement in qt_tree_model.py**

1. Replace `flags()` (lines 168-172):

```python
    def flags(self, index):
        if not index.isValid():
            return Qt.NoItemFlags
        col = self._manager.columns[index.column()]
        row = index.internalPointer()
        flags = col.view.get_flags(row)
        # Per-row column locks (issue #541): while any owner holds a
        # lock on this col_id, the cell is inert. Both flags must go —
        # checkbox cells are ItemIsUserCheckable, never ItemIsEditable.
        if row.is_column_locked(col.model.col_id):
            flags &= ~(Qt.ItemIsEditable | Qt.ItemIsUserCheckable)
        return flags
```

2. In `data()`, replace the BackgroundRole read-only check (lines 131-134) so it reads lock-aware flags, and add the tooltip role right after it:

```python
        # Read-only cells get the light-grey fill (mirror of protocol_grid
        # #359): read-only == neither editable nor user-checkable. The
        # active-row highlight above already returned for that row.
        # Reads self.flags(), not the view's raw get_flags, so per-row
        # column locks (issue #541) pick up the fill for free.
        if role == Qt.BackgroundRole:
            flags = self.flags(index)
            if not (flags & Qt.ItemIsEditable) and not (flags & Qt.ItemIsUserCheckable):
                return self._read_only_brush()

        # A locked cell explains itself: lock reasons are the tooltip.
        if role == Qt.ToolTipRole:
            reasons = node.column_lock_reasons(col.model.col_id)
            if reasons:
                return "\n".join(reasons)
            return None
```

3. Replace `_wire_row_observers` (lines 286-326) — the lock observer is wired for EVERY row, unconditionally (the old early-return when no column declared `depends_on_row_traits` goes away):

```python
    def _wire_row_observers(self):
        # Identify per-column row-trait dependencies once.
        col_trait_pairs: list = []
        for col_idx, col in enumerate(self._manager.columns):
            traits = list(getattr(col.view, "depends_on_row_traits", []) or [])
            for trait_name in traits:
                col_trait_pairs.append((col_idx, trait_name))

        live_rows = list(self._iter_all_rows())
        live_ids = {id(r) for r in live_rows}

        # Tear down handles for rows that are no longer in the tree.
        for row_id in list(self._row_observer_handles.keys()):
            if row_id in live_ids:
                continue
            row, handles = self._row_observer_handles.pop(row_id)
            for trait_name, handler in handles:
                try:
                    row.observe(handler, trait_name, remove=True)
                except Exception:
                    pass

        # Wire newcomers; skip rows already wired (Traits' observe is
        # idempotent on identical (handler, trait) but only if the
        # callable identity matches — partial() makes a new object each
        # call, so we MUST guard ourselves).
        for row in live_rows:
            if id(row) in self._row_observer_handles:
                continue
            handles: list = []
            # Column locks repaint centrally for every row (issue #541)
            # — a gated column never has to declare the dependency, so
            # the stale-grey-out class of bug can't recur.
            lock_handler = partial(self._on_row_locks_changed, row)
            row.observe(lock_handler, "column_locks")
            handles.append(("column_locks", lock_handler))
            for col_idx, trait_name in col_trait_pairs:
                if trait_name not in row.trait_names():
                    continue
                handler = partial(self._on_row_trait_changed, row, col_idx)
                row.observe(handler, trait_name)
                handles.append((trait_name, handler))
            self._row_observer_handles[id(row)] = (row, handles)
```

4. Add next to `_on_row_trait_changed` (line 328):

```python
    def _on_row_locks_changed(self, row, event):
        # A lock can gate any column on the row; one whole-row
        # dataChanged is cheaper than diffing which col_ids moved.
        top_left = self._index_for_cell(row, 0)
        if not top_left.isValid():
            return
        bottom_right = self._index_for_cell(row, len(self._manager.columns) - 1)
        self.dataChanged.emit(top_left, bottom_right)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: Step 2's command, plus the neighbours the rewiring touches:
`... -m pytest src/pluggable_protocol_tree/tests/test_column_locks.py src/pluggable_protocol_tree/tests/test_qt_model_reactive_wiring.py src/pluggable_protocol_tree/tests/test_qt_tree_model.py -q`
Expected: all PASS.

- [ ] **Step 5: Commit (after user approval)**

```bash
git add pluggable_protocol_tree/views/qt_tree_model.py pluggable_protocol_tree/tests/test_column_locks.py
git commit -m "feat(pluggable_protocol_tree): enforce column locks in MvcTreeModel

flags() clears ItemIsEditable|ItemIsUserCheckable on locked cells
(checkboxes are checkable, never editable, so both must go), lock
reasons render as the cell tooltip, and the grey read-only fill now
reads lock-aware flags. Repaint is auto-wired: the model observes
every row's column_locks itself, so gated columns never declare a
dependency and the stale-grey-out bug class can't recur.

Part of #541"
```

### Task 4: Bulk writes respect locks

**Files:**
- Modify: `pluggable_protocol_tree/models/row_manager.py` (`set_values`, line 602-605)
- Test: `pluggable_protocol_tree/tests/test_row_manager.py` (append near `test_set_values_bulk`, line 383)

**Interfaces:**
- Consumes: `is_column_locked` (Task 2).
- Produces: `set_values` (the Bulk Set dialog's only apply path — `views/tree_widget.py:526`) skips rows where the target column is locked. `set_value` (singular; programmatic DV-sync path) intentionally unchanged.

**Why:** `BulkSetDialog._build_column_row` checks flags on a throwaway TEMPLATE row (`bulk_set_dialog.py:96-99`) — that filters which *columns* are offered, but says nothing about per-row locks on the *targets*. Without this, bulk-ticking Capture would write straight through a fluorescence lock.

- [ ] **Step 1: Write the failing test**

Append to `pluggable_protocol_tree/tests/test_row_manager.py` after `test_set_values_bulk` (line 388):

```python
def test_set_values_skips_locked_rows(manager):
    """Bulk Set must not write what the per-cell editor would refuse:
    rows where the column is locked (issue #541) are skipped."""
    a = manager.add_step()
    b = manager.add_step()
    manager.get_row(b).lock_column("duration_s", owner="test", reason="held")
    manager.set_values([a, b], "duration_s", 4.2)
    assert manager.get_row(a).duration_s == 4.2
    assert manager.get_row(b).duration_s != 4.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_row_manager.py -q`
Expected: the new test FAILS (b gets 4.2); everything else passes.

- [ ] **Step 3: Implement the skip**

Replace `set_values` in `pluggable_protocol_tree/models/row_manager.py` (lines 602-605):

```python
    def set_values(self, paths: List[Path], col_id: str, value) -> None:
        """Bulk write — the Bulk Set dialog's apply path. Rows where the
        column is locked (issue #541) are skipped: a lock means some
        owner arbitrates that cell, and a bulk write must not bypass
        what the per-cell editor would refuse."""
        col = self._column_by_id(col_id)
        for path in paths:
            if self.get_row(path).is_column_locked(col.model.col_id):
                continue
            self._set_value(path, col, value)
```

- [ ] **Step 4: Run test to verify it passes**

Run: Step 2's command, plus `src/pluggable_protocol_tree/tests/test_bulk_set.py`. Expected: all PASS.

- [ ] **Step 5: Commit (after user approval)**

```bash
git add pluggable_protocol_tree/models/row_manager.py pluggable_protocol_tree/tests/test_row_manager.py
git commit -m "feat(pluggable_protocol_tree): bulk set skips locked cells

BulkSetDialog filters settable columns on a template row's flags,
which can't see per-row locks on the actual targets. Skip locked
rows in set_values so a bulk write can't bypass what the per-cell
editor refuses.

Part of #541"
```

### Task 5: Debt paid — `repeat_duration_controls` adopts the mechanism

**Files:**
- Modify: `pluggable_protocol_tree/models/row.py` (add observer on BaseRow)
- Modify: `pluggable_protocol_tree/builtins/repeat_duration_column.py` (handler gains the switch-back path; docstring)
- Modify: `pluggable_protocol_tree/builtins/route_repetitions_column.py` (RouteRepsHandler retires; docstring)
- Test: `pluggable_protocol_tree/tests/test_builtins.py` (rewrite lines 193-231), `pluggable_protocol_tree/tests/test_persistence.py` (append)

**Interfaces:**
- Consumes: `lock_column` / `unlock_column` (Task 2); flags enforcement (Task 3).
- Produces: whenever `repeat_duration_controls` flips (edit dialog, DV-sidebar sync at `services/device_viewer_sync.py:119-121`, protocol load at `services/persistence.py:167-169`), the `route_repetitions` cell locks/unlocks with owner `"repeat_duration"`. The mode-handoff dialog's promise — *"Route Reps will become read-only while Route Reps Dur is in control"* — becomes true.

**Behaviour change (deliberate):** with Route Reps genuinely read-only, its old prompt-and-reject `on_interact` arbitration (`RouteRepsHandler`) is unreachable from the UI and retires. The way BACK to count mode is editing **Route Reps Dur to 0** (0 already means "disabled" per the trait desc, and the DV sidebar already treats 0 exactly this way — `device_viewer_sync.py:119`), which now prompts with the same dialog text the Route Reps edit used to show.

- [ ] **Step 1: Write the failing tests**

In `pluggable_protocol_tree/tests/test_builtins.py`, DELETE `test_route_reps_handler_switch_back_from_duration_on_confirm` (lines 206-216) and `test_route_reps_handler_cancel_rejects_edit` (lines 219-230), keep `test_route_reps_handler_plain_write_when_not_in_duration_mode` (rename to `test_route_reps_plain_write_when_not_in_duration_mode` since the custom handler is gone — the default `BaseColumnHandler` write-through takes over; the body is unchanged and must still pass). Add in their place:

```python
def test_repeat_duration_flag_locks_route_reps_cell():
    """The mode-handoff dialog promises 'Route Reps will become
    read-only while Route Reps Dur is in control' — the flag now
    drives a column lock (issue #541 debt), on every path that flips
    it (edit dialog, DV-sidebar sync, protocol load)."""
    from pluggable_protocol_tree.models.row import BaseRow
    row = BaseRow()
    row.repeat_duration_controls = True
    assert row.is_column_locked("route_repetitions") is True
    assert row.column_lock_reasons("route_repetitions") == [
        "Route Reps Dur is in control"]
    row.repeat_duration_controls = False
    assert row.is_column_locked("route_repetitions") is False


def test_repeat_duration_zero_edit_switches_back_on_confirm(monkeypatch):
    """Route Reps Dur = 0 is the way back to count mode now that the
    Route Reps cell is genuinely read-only in duration mode."""
    import pluggable_protocol_tree.builtins.repeat_duration_column as mod
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.repeat_duration_column import (
        make_repeat_duration_column,
    )
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: mod.YES)
    col = make_repeat_duration_column()
    Row = build_row_type([col], base=BaseRow)
    row = Row()
    row.repeat_duration_controls = True
    assert col.handler.on_interact(row, col.model, 0.0) is True
    assert row.repeat_duration_controls is False
    assert row.is_column_locked("route_repetitions") is False
    assert row.repeat_duration == 0.0


def test_repeat_duration_zero_edit_cancel_stays_in_duration_mode(monkeypatch):
    import pluggable_protocol_tree.builtins.repeat_duration_column as mod
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.repeat_duration_column import (
        make_repeat_duration_column,
    )
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: 0)   # not YES
    col = make_repeat_duration_column()
    Row = build_row_type([col], base=BaseRow)
    row = Row()
    row.repeat_duration_controls = True
    row.repeat_duration = 30.0
    assert col.handler.on_interact(row, col.model, 0.0) is False
    assert row.repeat_duration_controls is True
    assert row.repeat_duration == 30.0


def test_repeat_duration_nonzero_edit_in_duration_mode_is_plain_write(monkeypatch):
    import pluggable_protocol_tree.builtins.repeat_duration_column as mod
    from pluggable_protocol_tree.models.row import build_row_type, BaseRow
    from pluggable_protocol_tree.builtins.repeat_duration_column import (
        make_repeat_duration_column,
    )
    monkeypatch.setattr(mod, "confirm", lambda *a, **k: (_ for _ in ()).throw(
        AssertionError("no dialog for a non-zero edit in duration mode")))
    col = make_repeat_duration_column()
    Row = build_row_type([col], base=BaseRow)
    row = Row()
    row.repeat_duration_controls = True
    assert col.handler.on_interact(row, col.model, 45.0) is True
    assert row.repeat_duration == 45.0
    assert row.repeat_duration_controls is True
```

Append to `pluggable_protocol_tree/tests/test_persistence.py` (after the `repeat_duration_controls` round-trip section, line ~152; reuse that section's existing column/serialize fixtures — read them first and follow their construction style):

```python
def test_column_locks_are_never_serialized():
    """Locks are runtime-derived; persisting one would strand a
    protocol opened without the owning plugin (issue #541)."""
    # Build a root + one step exactly as the neighbouring round-trip
    # tests in this section do, then:
    #   step.lock_column("route_repetitions", owner="repeat_duration",
    #                    reason="Route Reps Dur is in control")
    #   data = <this module's serialize helper>(root, columns)
    import json
    assert "column_locks" not in json.dumps(data)


def test_loading_row_flags_rebuilds_route_reps_lock():
    """persistence writes repeat_duration_controls directly onto the
    row; the BaseRow observer must rebuild the lock from it."""
    # Serialize a tree whose step has repeat_duration_controls=True
    # (again per the neighbouring tests), load it back, then:
    assert loaded_step.repeat_duration_controls is True
    assert loaded_step.is_column_locked("route_repetitions") is True
```

(The two persistence tests above name the intent; flesh out the fixture lines by copying the construction used in the `repeat_duration_controls round-trip via row_flags` section at line 152 of that file — same columns, same serialize/load helpers.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/pluggable_protocol_tree/tests/test_builtins.py src/pluggable_protocol_tree/tests/test_persistence.py -q`
Expected: new tests FAIL (no lock on flag flip; 0-edit writes without prompting); deleted tests gone.

- [ ] **Step 3: Implement**

1. `pluggable_protocol_tree/models/row.py` — add `observe` to the traits import, and this method on `BaseRow` (after `column_lock_reasons`):

```python
    @observe("repeat_duration_controls")
    def _sync_repeat_duration_lock(self, event):
        # "Route Reps will become read-only while Route Reps Dur is in
        # control" — the mode-handoff dialog's promise (issue #541
        # debt). Observed on the trait, not done in the column handler,
        # because DV-sidebar sync and protocol load write this flag
        # directly and the lock must follow on every path.
        if event.new:
            self.lock_column("route_repetitions", owner="repeat_duration",
                             reason="Route Reps Dur is in control")
        else:
            self.unlock_column("route_repetitions", owner="repeat_duration")
```

2. `pluggable_protocol_tree/builtins/repeat_duration_column.py` — replace the `already_controls` branch in `on_interact` (lines 47-48):

```python
        if already_controls:
            if new_value == 0.0:
                # 0 disables duration control (matches the DV sidebar,
                # which derives the flag from repeat_duration > 0) —
                # and it is the only way back now that the lock makes
                # Route Reps genuinely read-only in duration mode.
                choice = confirm(
                    None,
                    title="Switch to Route Reps Control",
                    message=(
                        "Setting Route Reps Dur to 0 hands loop control "
                        "back to Route Reps: routes loop until the largest "
                        "loop has completed all repetitions.<br><br>"
                        "Route Reps will become editable again."
                    ),
                    yes_label="Switch",
                    no_label="Cancel",
                )
                if choice != YES:
                    return False
                row.repeat_duration_controls = False
            return model.set_value(row, new_value)
```

Update the module docstring's last paragraph to note: flipping to True locks the `route_repetitions` cell (via the BaseRow observer); editing back to 0 prompts and unlocks.

3. `pluggable_protocol_tree/builtins/route_repetitions_column.py` — delete `RouteRepsHandler` (lines 31-52) and the now-unused `from microdrop_application.dialogs.pyface_wrapper import YES, confirm` and `BaseColumnHandler` imports; drop `handler=RouteRepsHandler(),` from the factory (the `Column` default handler is the plain write-through, same as `repetitions_column.py`). Rewrite the docstring's second paragraph:

```
While a row is in duration-controlled mode (``repeat_duration_controls``
True) this cell is LOCKED read-only via the per-row column-lock
mechanism (issue #541) — the lock is applied by a BaseRow observer on
the flag, so it also holds on protocol load and DV-sidebar sync. The
way back to count mode is editing Route Reps Dur to 0, which prompts
(see repeat_duration_column.py). No custom handler remains: edits can
only happen in count mode, where they are plain writes.
```

- [ ] **Step 4: Run tests to verify they pass**

Run: Step 2's command plus `src/pluggable_protocol_tree/tests/test_row.py src/pluggable_protocol_tree/tests/test_electrodes_routes_columns.py` (the latter flips the flag on rows heavily — must stay green).
Expected: all PASS.

- [ ] **Step 5: Commit (after user approval)**

```bash
git add pluggable_protocol_tree/models/row.py pluggable_protocol_tree/builtins/repeat_duration_column.py pluggable_protocol_tree/builtins/route_repetitions_column.py pluggable_protocol_tree/tests/test_builtins.py pluggable_protocol_tree/tests/test_persistence.py
git commit -m "feat(pluggable_protocol_tree): route reps lock honors mode dialog

The Route Reps Dur handoff dialog promised 'Route Reps will become
read-only' but the cell stayed editable, arbitrated by prompt-and-
reject. A BaseRow observer on repeat_duration_controls now drives a
real column lock, so the promise holds on every path that flips the
flag (edit, DV-sidebar sync, protocol load). The way back to count
mode is Route Reps Dur = 0, which prompts; RouteRepsHandler retires.

Part of #541"
```

### Task 6: Latent bug — `capture_at` repaint dependency; PR

**Files:**
- Modify: `video_protocol_controls/protocol_columns/capture_column.py` (CaptureAtComboBoxView, line 77-97; imports line 29)
- Test: `video_protocol_controls/tests/test_capture_column.py` (append)

**Interfaces:**
- Consumes: the existing `depends_on_row_traits` wiring in `MvcTreeModel._wire_row_observers`.
- Produces: toggling `row.capture` immediately repaints the `capture_at` cell's grey-out.

**Note (deviation from the issue's wording):** the issue says central auto-wiring fixes this, but the auto-wiring covers the `column_locks` trait only — `capture_at`'s grey-out is a pure function of the plain `capture` trait, for which the right tool is the existing declarative dependency (`force_column.py`'s `depends_on_row_traits = ["voltage"]` precedent). Locks are wrong here: they're owner-driven runtime state and nothing would rebuild them on load. State this in the PR body.

- [ ] **Step 1: Write the failing test**

Append to `video_protocol_controls/tests/test_capture_column.py`:

```python
def test_capture_at_view_declares_capture_dependency():
    """CaptureAtComboBoxView gates flags + display on row.capture; without
    this declaration its grey-out only refreshed on an incidental
    repaint (issue #541 latent bug)."""
    from video_protocol_controls.protocol_columns.capture_column import (
        CaptureAtComboBoxView,
    )
    assert list(CaptureAtComboBoxView().depends_on_row_traits) == ["capture"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "C:/Users/Info/PycharmProjects/pixi-microdrop/microdrop-py" && QT_QPA_PLATFORM=offscreen pixi run python -m pytest src/video_protocol_controls/tests/test_capture_column.py -q`
Expected: the new test FAILS (attribute missing/empty).

- [ ] **Step 3: Implement**

In `video_protocol_controls/protocol_columns/capture_column.py`: extend the traits import (line 29) to `from traits.api import Bool, Enum, List, Str`, and add to `CaptureAtComboBoxView` (before `_options_default`):

```python
    #: get_flags/format_display above are pure functions of row.capture;
    #: declare it so the tree model repaints this cell the moment the
    #: checkbox toggles (issue #541 latent bug — previously the grey-out
    #: waited for an incidental repaint).
    depends_on_row_traits = List(Str, value=["capture"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: Step 2's command. Expected: all PASS.

- [ ] **Step 5: Commit (after user approval), push, PR**

```bash
git add video_protocol_controls/protocol_columns/capture_column.py video_protocol_controls/tests/test_capture_column.py
git commit -m "fix(video_protocol_controls): repaint capture_at on capture toggle

CaptureAtComboBoxView gates editability and display on row.capture
but never declared depends_on_row_traits, so its grey-out waited for
an incidental repaint. Declare the dependency (force_column
precedent).

Part of #541"
git push -u origin feat/541-per-row-column-locks
gh pr create --repo Blue-Ocean-Technologies-Inc/Microdrop \
  --title "feat(pluggable_protocol_tree): generic per-row column locks" \
  --body "..."   # cover: storage/enforcement/tooltip/repaint/no-persistence,
                 # the repeat_duration adoption + Route-Reps-Dur=0 switch-back
                 # behaviour change, the bulk-set skip, the capture_at fix and
                 # the auto-wiring-vs-declared-dependency deviation. Closes #541.
```

---

## Self-Review Notes

- **Spec coverage (#542):** arbitrary N choices via `RESULT_CUSTOM_1 + i` ✔; returns caller's label not an int ✔; Escape/close → unambiguous `None` ✔; parent/title/`(result, checked)` conventions ✔.
- **Spec coverage (#541):** owner-keyed storage + API ✔ (Task 2); central `flags()` clearing both flags ✔, tooltip ✔, grey fill (via `self.flags`, a required fix the issue implies but doesn't spell out) ✔, bulk-set dialog per-row gap closed in `set_values` ✔ (Tasks 3–4); auto-wired repaint ✔ (Task 3); not serialized ✔ (Task 5 test); debt paid ✔ (Task 5, with the Route-Reps-Dur=0 switch-back as the necessary new escape hatch); latent bug retired ✔ (Task 6, via declared dependency rather than locks — deviation documented).
- **Type consistency:** `lock_column/unlock_column/is_column_locked/column_lock_reasons` names and signatures match across Tasks 2/3/4/5 and the fluorescence design doc's planned call sites; owner string `"repeat_duration"` and reason `"Route Reps Dur is in control"` used identically in Task 5 code and tests.
- **Known executor judgement points:** the two persistence tests in Task 5 intentionally defer fixture details to the neighbouring tests in `test_persistence.py` (read that section first); everything else is verbatim.
