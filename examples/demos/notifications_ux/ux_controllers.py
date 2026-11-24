# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The prototype's controllers: the drawer's requests (the product's, plus
the second button, the "new" marker and acting on a card), and the toasts'
arrivals and timing. Qt-free; the views follow the models."""

# Standard library imports.
import time

# Enthought library imports.
from pyface.timer.api import CallbackTimer
from traits.api import Any, Bool, Callable, Float, HasTraits, Instance, observe

# Microdrop package imports.
from notifications.consts import SEVERITY_ERROR, SEVERITY_SUCCESS
from notifications.controllers.notifications_controller import NotificationsController

# Local imports.
from .ux_consts import (
    NEWS_SECTION_ID,
    QUIET_SUMMARY_SOURCE,
    TOAST_LIMIT,
    TOAST_TICK_MS,
    HelpAction,
    SnoozeAction,
)
from .ux_models import ToastItem, UxPaneModel


class UxNotificationsController(NotificationsController):
    """The product controller, plus the prototype's card behaviour."""

    pane_model = Instance(UxPaneModel, ())

    #: ``open_tutorial(name)`` for a HelpAction.
    open_tutorial = Callable()

    @observe("pane_model:run_action")
    def _run_action(self, event):
        """Do what the button says, then the card counts as handled: read,
        out of Needs attention, its buttons replaced by what was done."""
        entry = event.new

        # Handled first, so its toast has left before any answer arrives.
        entry.trait_set(acted=entry.action.label, needs_attention=False, unread=False)

        super()._run_action(event)

    @observe("pane_model:mark_all_read_button")
    def _mark_all_read(self, event):
        """Read everything, and drop the open drawer's "new" marks too."""
        center = self.pane_model.center

        center.update_all(
            [entry for entry in center.entries if entry.unread or entry.is_new],
            unread=False,
            is_new=False,
        )

    @observe("pane_model:run_secondary_action")
    def _run_secondary_action(self, event):
        entry = event.new
        action = entry.secondary_action

        # Help: read, yet still to do, so it stays in Needs attention until
        # dismissed or the condition clears; a tutorial changes nothing.
        if isinstance(action, HelpAction):
            entry.unread = False

            if self.open_tutorial is not None:
                self.open_tutorial(action.tutorial)

        # Later: out of Needs attention, into the list, still to do.
        elif isinstance(action, SnoozeAction):
            entry.trait_set(needs_attention=False, unread=False)

    # Events and plain traits, not the centre's unread_count: a Property
    # changed again while its own change is being announced can leave its
    # later observers with the stale value.
    @observe("pane_model:is_open")
    @observe("pane_model:center:[arrived, repeated]")
    def _read_while_open(self, event):
        """Opening the drawer marks the unread entries seen, and new until it
        closes; what arrives while it is open is new too. Closing it drops
        the marks."""
        center = self.pane_model.center

        if self.pane_model.is_open and event.name == "is_open":
            unread = [entry for entry in center.entries if entry.unread]
            center.update_all(unread, is_new=True, unread=False)

        elif self.pane_model.is_open and event.new.unread:
            event.new.trait_set(is_new=True, unread=False)

        elif event.name == "is_open":
            marked = [entry for entry in center.entries if entry.is_new]
            center.update_all(marked, is_new=False)

        if event.name == "is_open":
            self._see_feed()

    @observe("pane_model:sections:items:expanded")
    def _see_feed_when_expanded(self, event):

        if event.object.id == NEWS_SECTION_ID:
            self._see_feed()

    def _see_feed(self):
        """New posts are seen once the drawer is open on an expanded News:
        off the bell, still marked new; closing the drawer lets go of
        them."""
        model = self.pane_model
        news = next((s for s in model.sections if s.id == NEWS_SECTION_ID), None)

        if model.is_open and news is not None and news.expanded:
            for entry in model.feed_alerts:
                if entry.unread:
                    entry.trait_set(unread=False, is_new=True)

        elif not model.is_open:
            model.feed_alerts = [entry for entry in model.feed_alerts if entry.unread]


class ToastStackController(HasTraits):
    """Turns arrivals into toasts and runs their timers.

    A toast shows for each new (or newly unread) notification while the
    drawer is closed, at most TOAST_LIMIT at once; the rest go straight to
    the bell, counted as the stack's overflow. Info and success toasts leave
    after the settings' timeout of not being hovered, if the settings say
    toasts time out; sticky ones stay. While the stack is quiet only errors
    and Needs attention items pop up; the rest are held, and one summary
    toast says how many when it ends.
    """

    #: The drawer's model: its centre, toasts and open state.
    pane_model = Instance(UxPaneModel)

    #: Off until the toasts' view is on the window: what is posted while
    #: the app starts is history, not news.
    enabled = Bool(False)

    #: Ticks while any toast counts down.
    _timer = Any()

    #: time.monotonic() of the last tick.
    _last_tick = Float()

    # ------------------------------------------------------------------ #
    # Public interface                                                    #
    # ------------------------------------------------------------------ #

    def dismiss(self, item):
        """The toast's cross: into the bell, still unread."""
        item.trait_set(into_bell=True, leaving=True)

    def act(self, item):
        """The toast's card was acted on: it leaves, not into the bell."""
        item.trait_set(into_bell=False, leaving=True)

    def clear(self):
        """Take every toast off at once (the drawer opened, or a reset)."""
        toasts = self.pane_model.toasts

        for item in toasts.items:
            item.trait_set(into_bell=False, leaving=True)

        toasts.overflow_entries = []

    # ------------------------------------------------------------------ #
    # Arrivals                                                            #
    # ------------------------------------------------------------------ #

    @observe("pane_model:center:arrived")
    def _show_arrival(self, event):
        self.offer(event.new)

    def offer(self, entry):
        """Pop ``entry`` up, hold it while quiet, or count it past the
        limit, ringing the bell for what is news; while the drawer is open
        only errors and Needs attention items ring."""
        toasts = self.pane_model.toasts
        urgent = entry.severity == SEVERITY_ERROR or entry.needs_attention

        if not self.enabled:
            return

        if self.pane_model.is_open:
            if urgent:
                self.pane_model.rang = entry

            return

        if not entry.unread:
            return

        item = toasts.find(entry)

        if item is not None and not item.leaving:
            item.remaining_ms = toasts.settings.timeout_ms

            return

        # While quiet, the quiet run's own categories still come through.
        kind = toasts.settings.category(entry.category_id)
        own = kind is not None and kind.group == toasts.quiet_reason

        if toasts.quiet and not urgent and not own:
            if entry not in toasts.held:
                toasts.held.append(entry)

            return

        self.pane_model.rang = entry

        # Pop-ups off for its category: straight to the bell.
        if kind is not None and not kind.popup and not urgent:
            return

        showing = [item for item in toasts.items if not item.leaving]

        if len(showing) >= TOAST_LIMIT:
            toasts.overflow_entries.append(entry)

            return

        toasts.items.append(
            ToastItem(entry=entry, remaining_ms=toasts.settings.timeout_ms)
        )
        self._start_timer()

    @observe("pane_model:center:repeated")
    def _refresh_repeat(self, event):
        toasts = self.pane_model.toasts
        item = toasts.find(event.new)

        if item is not None and not item.leaving:
            item.remaining_ms = toasts.settings.timeout_ms

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
        entries = self.pane_model.center.entries

        for item in self.pane_model.toasts.items:
            listed = item.entry in entries or item.entry.feed_post_id

            if not listed and not item.leaving:
                item.trait_set(into_bell=False, leaving=True)

    @observe("pane_model:toasts:items:items:entry:[acted, unread]")
    def _leave_when_handled(self, event):
        """A card acted on, or read elsewhere, needs no toast."""

        for item in self.pane_model.toasts.items:
            entry = item.entry

            if not item.leaving and (entry.acted or not entry.unread):
                item.trait_set(into_bell=False, leaving=True)

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
        counting = False

        self._last_tick = now

        toasts = self.pane_model.toasts

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
