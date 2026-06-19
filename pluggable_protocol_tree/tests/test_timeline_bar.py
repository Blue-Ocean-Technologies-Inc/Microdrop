"""TimelineBar is a pure rendering/intent widget: it paints a step track
(one tick per step) plus a phase track for the current step, and emits
step_seek_requested / phase_seek_requested when the user clicks a track.
It holds no engine references and performs no seeking itself."""

from pyface.qt.QtCore import QPoint
from pluggable_protocol_tree.views.timeline_bar import SIDE_MARGIN, TimelineBar

WIDTH = 400


def _bar(qapp, labels=("S0", "S1", "S2", "S3")):
    bar = TimelineBar()
    bar.rebuild(list(labels))
    bar.resize(WIDTH, bar.height())
    return bar


def test_rebuild_sets_step_count(qapp):
    bar = _bar(qapp)
    assert bar.step_count == 4


def test_step_index_at_x_maps_across_width(qapp):
    bar = _bar(qapp)
    # 4 steps across the usable width -> first quarter is step 0, last is 3.
    assert bar._step_index_at_x(bar._step_track_rect().left() + 1) == 0
    assert bar._step_index_at_x(bar._step_track_rect().right() - 1) == 3


def test_step_index_at_x_is_clamped(qapp):
    bar = _bar(qapp)
    assert bar._step_index_at_x(-50) == 0
    assert bar._step_index_at_x(WIDTH + 50) == 3


def test_click_on_step_track_emits_step_seek(qapp):
    bar = _bar(qapp)
    bar.set_position(0, 4, 0, 0)
    captured = []
    bar.step_seek_requested.connect(captured.append)
    r = bar._step_track_rect()
    bar._seek_at_point(QPoint(r.right() - 1, r.center().y()))
    assert captured == [3]


def test_phase_track_hidden_without_multiple_phases(qapp):
    bar = _bar(qapp)
    bar.set_running(True)
    bar.set_position(1, 4, 0, 1)  # phase_total == 1 -> no phase track
    assert bar._phase_track_visible() is False


def test_phase_track_hidden_when_not_running(qapp):
    bar = _bar(qapp)
    bar.set_position(1, 4, 0, 5)  # 5 phases, but idle -> phase track hidden
    assert bar._phase_track_visible() is False
    captured = []
    bar.phase_seek_requested.connect(captured.append)
    r = bar._phase_track_rect()
    bar._seek_at_point(QPoint(r.right() - 1, r.center().y()))
    assert captured == []  # clicks in the phase band don't seek when hidden


def test_click_on_phase_track_emits_phase_seek(qapp):
    bar = _bar(qapp)
    bar.set_running(True)
    bar.set_position(1, 4, 0, 5)  # running on a step with 5 phases
    assert bar._phase_track_visible() is True
    captured = []
    bar.phase_seek_requested.connect(captured.append)
    r = bar._phase_track_rect()
    bar._seek_at_point(QPoint(r.right() - 1, r.center().y()))
    assert captured == [4]


def test_phase_index_at_x_maps_across_width(qapp):
    bar = _bar(qapp)
    bar.set_position(1, 4, 0, 5)  # current step has 5 phases
    # 5 phases across the usable width -> first is phase 0, last is 4.
    assert bar._phase_index_at_x(bar._phase_track_rect().left() + 1) == 0
    assert bar._phase_index_at_x(bar._phase_track_rect().right() - 1) == 4


def test_set_running_does_not_break_interaction(qapp):
    bar = _bar(qapp)
    bar.set_position(0, 4, 0, 0)
    bar.set_running(True)
    captured = []
    bar.step_seek_requested.connect(captured.append)
    r = bar._step_track_rect()
    bar._seek_at_point(QPoint(r.left() + 1, r.center().y()))
    assert captured == [0]


def test_group_cells_get_alternating_colors(qapp):
    bar = TimelineBar()
    bar.rebuild(["A", "B", "C", "D"], group_keys=[None, (1,), (1,), (2,)])
    assert bar._cell_colors[0] is None                  # ungrouped step
    assert bar._cell_colors[1] == bar._cell_colors[2]   # same group -> same colour
    assert bar._cell_colors[1] != bar._cell_colors[3]   # different group -> different


def test_drag_moves_relative_to_current_step(qapp):
    bar = _bar(qapp)
    bar.set_position(1, 4, 0, 0)   # current step index 1 (the drag anchor)
    captured = []
    bar.step_seek_requested.connect(captured.append)
    y = bar._step_track_rect().center().y()
    seg = bar._usable_width() / bar.step_count
    bar._begin_drag(QPoint(int(SIDE_MARGIN + 0.5 * seg), y))
    # Drag right by ~2 cells from the press point -> anchor 1 + 2 = 3,
    # regardless of which absolute cell the cursor is over.
    bar._drag_update(QPoint(int(SIDE_MARGIN + 2.5 * seg), y))
    assert captured[-1] == 3
