# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Arrivals turned into toasts, and the toasts' timers. Qt-free: the toast
view follows the model."""

# Standard library imports.
import time

# Enthought library imports.
from pyface.timer.api import CallbackTimer
from traits.api import Any, Bool, Float, HasTraits, Instance, observe

# Local imports.
from ..consts import SEVERITY_ERROR, SEVERITY_SUCCESS
from ..models.notifications_pane_model import NotificationsPaneModel
from ..models.toasts import ToastItem

#: Toasts shown at once; the rest go straight to the bell, counted on a
#: "+N more" pill above the stack.
TOAST_LIMIT = 3

#: Countdown resolution (ms) of the toasts' timers.
TOAST_TICK_MS = 50

#: What an arrival that rings does: pops a toast up (or counts past the
#: limit, or goes straight to the bell), refreshes the toast already
#: showing (a repeat, its count up), or lands in the open drawer.
ARRIVAL_POP_UP = "pop up"
ARRIVAL_REFRESH = "refresh"
ARRIVAL_IN_DRAWER = "in drawer"

#: The outcomes that ring the bell (and chime).
RINGING_ARRIVALS = (ARRIVAL_POP_UP, ARRIVAL_REFRESH, ARRIVAL_IN_DRAWER)

#: Why an arrival made no sound: any other outcome.
SKIP_START_UP = "start-up history"
SKIP_READ = "already read"
SKIP_QUIET = "quiet"

#: Who posts the summary when a quiet run ends.
QUIET_SUMMARY_SOURCE = "notifications"


def arrival_outcome(enabled, drawer_open, unread, toast_showing, held_quietly):
    """What an arrival (new, or a repeat of an entry already listed) does.

    It rings whenever something visible happens: a toast pops up, the toast
    already showing is refreshed (its count goes up, its time restarts), or
    it lands in the open drawer. It is silent only when nothing is seen:
    start-up history, an entry already read, one held while quiet."""

    if not enabled:
        return SKIP_START_UP

    if drawer_open:
        return ARRIVAL_IN_DRAWER

    if not unread:
        return SKIP_READ

    if toast_showing:
        return ARRIVAL_REFRESH

    if held_quietly:
        return SKIP_QUIET

    return ARRIVAL_POP_UP


class ToastStackController(HasTraits):
    """Turns arrivals into toasts and runs their timers.

    A toast shows for each new (or newly unread) notification while the
    drawer is closed, at most TOAST_LIMIT at once; the rest go straight to
    the bell, counted as the stack's overflow. Info and success toasts leave
    after the settings' timeout of not being hovered, if the settings say
    toasts time out; sticky ones stay. While quiet, only errors, Needs
    attention items and the quiet run's own categories pop up; the rest are
    held, and one summary toast says how many when quiet ends.
    """

    #: The drawer's model: its centre, toasts and open state.
    pane_model = Instance(NotificationsPaneModel)

    #: Off until the toasts can show on the main window: what is posted
    #: while the app starts is history, not news.
    enabled = Bool(False)

    #: Ticks while any toast counts down; made on first use.
    _timer = Any()

    #: time.monotonic() of the last tick.
    _last_tick = Float()

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def dismiss(self, item):
        """The toast's cross: into the bell, still unread. A section's
        alert hears of it."""
        item.trait_set(into_bell=True, leaving=True)

        if item.entry.alert is not None:
            item.entry.alert.dismissed = True

    def clear(self):
        """Take every toast off at once (the drawer opened, or a reset)."""
        toasts = self.pane_model.toasts

        for item in toasts.items:
            item.trait_set(into_bell=False, leaving=True)

        toasts.overflow_entries = []

    def offer(self, entry):
        """Pop ``entry`` up, refresh its toast, hold it while quiet, or count
        it past the limit; ring the bell (and chime) whenever that shows,
        and report what does not ring as ``silenced``, with why."""
        model = self.pane_model
        toasts = model.toasts
        settings = toasts.settings
        urgent = entry.severity == SEVERITY_ERROR or entry.needs_attention
        item = toasts.find(entry)
        showing = item is not None and not item.leaving

        # While quiet, the quiet run's own categories still come through.
        kind = settings.category(entry.category_id)
        own = kind is not None and kind.group == toasts.quiet_reason
        held = toasts.quiet and not urgent and not own

        outcome = arrival_outcome(
            self.enabled, model.is_open, entry.unread, showing, held
        )

        if outcome not in RINGING_ARRIVALS:
            if outcome == SKIP_QUIET and entry not in toasts.held:
                toasts.held.append(entry)

            model.silenced = (entry, outcome)

            return

        model.rang = entry

        # A refreshed toast counts down afresh; its entry may have changed
        # from one that stays (a warning) to one that times out.
        if outcome == ARRIVAL_REFRESH:
            item.remaining_ms = settings.timeout_ms
            self._start_timer()

        if outcome != ARRIVAL_POP_UP:
            return

        # Pop-ups off for its category: straight to the bell.
        if kind is not None and not kind.popup and not urgent:
            return

        self._pop_up(entry)

    # ------------------------------------------------------------------ #
    # Arrivals                                                            #
    # ------------------------------------------------------------------ #

    @observe("pane_model:center:[arrived, repeated]")
    def _show_arrival(self, event):
        """A repeat is an arrival like any other: its toast refreshes, or
        pops up again if it had gone."""
        self.offer(event.new)

    @observe("pane_model:toasts:settings:[auto_dismiss, auto_dismiss_seconds]")
    def _apply_settings(self, event):
        """Applies to the toasts showing: each counts down afresh, or stays."""
        toasts = self.pane_model.toasts

        for item in toasts.items:
            if not item.leaving:
                item.remaining_ms = toasts.settings.timeout_ms

        self._start_timer()

    @observe("pane_model:toasts:quiet")
    def _summarise_quiet_run(self, event):
        """The quiet run ended: one toast for what was held."""
        toasts = self.pane_model.toasts
        held, toasts.held = toasts.held, []

        if event.new or not held:
            return

        count = len(held)
        noun = "notification" if count == 1 else "notifications"

        self.pane_model.center.post(
            f"{toasts.quiet_reason} finished · {count} {noun} while running",
            detail="\n".join(f"• {entry.title}" for entry in held),
            severity=SEVERITY_SUCCESS,
            category="protocol",
            source=QUIET_SUMMARY_SOURCE,
        )

    @observe("pane_model:is_open")
    def _clear_when_drawer_opens(self, event):

        if event.new:
            self.clear()

    @observe("pane_model:center:entries.items")
    def _drop_toasts_of_dismissed_entries(self, event):
        entries = set(map(id, self.pane_model.center.entries))

        for item in self.pane_model.toasts.items:
            listed = id(item.entry) in entries or item.entry.section_id

            if not listed and not item.leaving:
                item.trait_set(into_bell=False, leaving=True)

    @observe("pane_model:toasts:items:items:entry:[acted, unread]")
    def _leave_when_handled(self, event):
        """A card acted on, or read elsewhere, needs no toast."""

        for item in self.pane_model.toasts.items:
            entry = item.entry

            if not item.leaving and (entry.acted or not entry.unread):
                item.trait_set(into_bell=False, leaving=True)

    def _pop_up(self, entry):
        toasts = self.pane_model.toasts
        on_screen = [item for item in toasts.items if not item.leaving]

        if len(on_screen) >= TOAST_LIMIT:
            if entry not in toasts.overflow_entries:
                toasts.overflow_entries.append(entry)

            return

        toasts.items.append(
            ToastItem(entry=entry, remaining_ms=toasts.settings.timeout_ms)
        )
        self._start_timer()

    # ------------------------------------------------------------------ #
    # Timing                                                              #
    # ------------------------------------------------------------------ #

    def _start_timer(self):

        if self._timer is None:
            self._timer = CallbackTimer(
                interval=TOAST_TICK_MS / 1000, callback=self._tick, repeat=None
            )

        if not self._timer.active:
            self._last_tick = time.monotonic()
            self._timer.start()

    def _tick(self):
        now = time.monotonic()
        elapsed_ms = int((now - self._last_tick) * 1000)
        toasts = self.pane_model.toasts
        counting = False

        self._last_tick = now

        for item in toasts.items:
            if item.leaving or not toasts.times_out(item):
                continue

            counting = True

            if item.hovered:
                continue

            item.remaining_ms = max(item.remaining_ms - elapsed_ms, 0)

            if not item.remaining_ms:
                item.trait_set(into_bell=True, leaving=True)

        if not counting:
            self._timer.stop()
