# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# Standard library imports.
import json
import os
import time

# Third-party imports.
try:
    import pygame
except Exception:
    pygame = None

# Enthought library imports.
from pyface.qt.QtCore import QTimer
from pyface.qt.QtWidgets import QGraphicsView
from traits.api import Bool, Float, HasTraits, Instance, Str, observe

# Microdrop package imports.
from device_viewer.consts import (
    GAMEPAD_AXIS_THRESHOLD,
    GAMEPAD_BTN_ADD,
    GAMEPAD_BTN_CLEAR,
    GAMEPAD_BTN_FIND,
    GAMEPAD_BTN_REALTIME,
    GAMEPAD_BTN_REMOVE,
    GAMEPAD_BTN_SPLIT,
    GAMEPAD_DEBOUNCE_ADD_REMOVE_S,
    GAMEPAD_DEBOUNCE_FIND_S,
    GAMEPAD_DEBOUNCE_MOVE_SPLIT_S,
    GAMEPAD_DEBOUNCE_REALTIME_S,
    GAMEPAD_IDLE_POLL_INTERVAL_MS,
    GAMEPAD_POLL_INTERVAL_MS,
)
from device_viewer.models.main_model import DeviceViewMainModel
from dropbot_controller.consts import DETECT_DROPLETS, SET_REALTIME_MODE

# Microdrop style imports.
from microdrop_style.colors import GREY, SUCCESS_COLOR

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from ..preferences import DeviceViewerPreferences
from .electrode_stepping_service import ElectrodeSteppingService

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class GamepadInteractionService(HasTraits):
    """Drive electrode stepping, split, and realtime toggling from a gamepad.

    Polls pygame (SDL) for controller events on a Qt timer, resolves the
    button mapping and debounce timings from env vars / preferences /
    defaults, supports live rebinding, and reports state through the app
    status bar (transient HUD messages while a controller is attached, and
    the persistent joystick icon). Not an Envisage service; the device-viewer
    dock pane builds one per loaded device only while the gamepad preference
    is on, so pygame is never initialized otherwise.
    """

    #: Device view Model
    model = Instance(DeviceViewMainModel)

    #: The current device view; parents the poll timer so Qt bounds its lifetime
    device_view = Instance(QGraphicsView)

    #: The preferences for the current device view
    device_viewer_preferences = Instance(DeviceViewerPreferences)

    #: Electrode cursor actions the D-pad drives; shared with the keyboard
    #: handlers of the interaction service
    stepping = Instance(ElectrodeSteppingService)

    #: Optional: status bar manager for HUD messages
    status_bar_manager = Instance(object, allow_none=True)

    #: Optional: persistent joystick indicator (QLabel) on the app status
    #: bar. Created and contributed by the device-viewer dock pane; this
    #: service only recolors it and sets its tooltip.
    gamepad_icon = Instance(object, allow_none=True)

    _hud_message = Str("")

    _split_modifier_down = Bool(
        False, desc="When True (B held), arrow presses are split steps."
    )
    _add_modifier_down = Bool(
        False, desc="When True (Y held), arrows extend active electrodes."
    )
    _remove_modifier_down = Bool(
        False, desc="When True (X held), arrows shrink active electrodes."
    )

    _axis_left_pressed = Bool(False)
    _axis_right_pressed = Bool(False)
    _axis_up_pressed = Bool(False)
    _axis_down_pressed = Bool(False)

    # pygame backend state (used when QtGamepad isn't available)
    _pygame_enabled = Bool(False)
    _pygame_timer = Instance(object, allow_none=True)
    _pygame_joystick = Instance(object, allow_none=True)
    _pygame_dpad_x_axis = Instance(int, allow_none=True)
    _pygame_dpad_y_axis = Instance(int, allow_none=True)
    _pygame_axis_threshold = Instance(float, allow_none=True)
    _btn_clear = Instance(int, allow_none=True)
    _btn_find_liquid = Instance(int, allow_none=True)
    _btn_split = Instance(int, allow_none=True)
    _btn_add_modifier = Instance(int, allow_none=True)
    _btn_remove_modifier = Instance(int, allow_none=True)
    _btn_realtime_toggle = Instance(int, allow_none=True)

    # Live button-capture (remap) state. When _capture_action is a non-empty
    # action name, the next gamepad button press is bound to that action instead
    # of triggering its normal behaviour. _capture_deadline expires the request.
    _capture_action = Str("")
    _capture_deadline = Float(0.0)

    #: Single source of truth for the button mapping, keyed by capture action
    #: name. Each entry is (preferences trait, env override key, live attribute,
    #: built-in default). Used by both _load_gamepad_mapping (read) and
    #: _finish_button_capture (write-back), so the two can't drift apart.
    _GAMEPAD_ACTIONS = {
        "clear": (
            "gamepad_btn_clear",
            "MICRODROP_GAMEPAD_BTN_CLEAR",
            "_btn_clear",
            GAMEPAD_BTN_CLEAR,
        ),
        "find": (
            "gamepad_btn_find",
            "MICRODROP_GAMEPAD_BTN_FIND",
            "_btn_find_liquid",
            GAMEPAD_BTN_FIND,
        ),
        "split": (
            "gamepad_btn_split",
            "MICRODROP_GAMEPAD_BTN_SPLIT",
            "_btn_split",
            GAMEPAD_BTN_SPLIT,
        ),
        "add": (
            "gamepad_btn_add",
            "MICRODROP_GAMEPAD_BTN_ADD_MOD",
            "_btn_add_modifier",
            GAMEPAD_BTN_ADD,
        ),
        "remove": (
            "gamepad_btn_remove",
            "MICRODROP_GAMEPAD_BTN_REMOVE_MOD",
            "_btn_remove_modifier",
            GAMEPAD_BTN_REMOVE,
        ),
        "realtime": (
            "gamepad_btn_realtime",
            "MICRODROP_GAMEPAD_BTN_REALTIME_TOGGLE",
            "_btn_realtime_toggle",
            GAMEPAD_BTN_REALTIME,
        ),
    }

    def traits_init(self):
        # Per-action debounce (seconds) + analog-stick threshold, resolved from
        # env vars / preferences / defaults. Loaded before controller setup.
        self._load_gamepad_timing()

        # Per-category last-action timestamps (independent debounce).
        self._last_dpad_action_ts = 0.0
        self._last_find_liquid_ts = 0.0
        self._last_realtime_toggle_ts = 0.0

        # Controller support via pygame (SDL). Loads the button mapping and
        # acquires a controller if one is attached.
        self.setup_pygame_gamepad_support()

        # Realtime-mode state is read from the shared model (model.realtime_mode),
        # which is kept in sync via REALTIME_MODE_UPDATED. No local mirror here:
        # a private flag would drift out of sync with the mouse-driven checkbox.

    def _set_hud(self, text: str) -> None:
        """Show ``text`` as the transient status-bar HUD message.

        Only while a controller is attached: without one the mouse-driven UI
        already shows every state the HUD would repeat.
        """
        mgr = getattr(self, "status_bar_manager", None)
        if mgr is None or not self._pygame_enabled:
            return
        try:
            # Remove the previous HUD message if present.
            if self._hud_message:
                try:
                    mgr.remove(self._hud_message)
                except Exception:
                    try:
                        mgr.messages = [
                            m for m in mgr.messages if m != self._hud_message
                        ]
                    except Exception:
                        pass
            self._hud_message = text
            try:
                mgr.messages += [text]
            except Exception:
                # Fallback: set persistent message if list interface differs.
                mgr.message = text
        except Exception:
            pass

    def _set_gamepad_indicator(self, text: str) -> None:
        """Color/tooltip the persistent joystick icon on the app status bar.

        Empty ``text`` shows the disconnected state. Unlike ``_set_hud`` (a
        transient, rotating action message), this is a persistent connection
        state: connected = the same green as the other status-bar icons with
        the controller name as tooltip; disconnected = a theme-independent
        light gray that reads correctly on both status-bar backgrounds.
        """
        icon = self.gamepad_icon
        if icon is None:
            return
        try:
            connected = bool(text)
            color = SUCCESS_COLOR if connected else GREY["lighter"]
            icon.setStyleSheet(f"color: {color};")
            icon.setToolTip(text if connected else "Gamepad disconnected")
        except RuntimeError as e:  # icon deleted with the window
            logger.debug(f"gamepad indicator gone: {e}")

    @observe("gamepad_icon")
    def _on_gamepad_icon_set(self, event):
        """Re-apply the connection state when the joystick icon arrives.

        The icon is None when this service is constructed (the dock pane
        creates and contributes it once the status bar exists) and is pushed
        in later. Without this, a controller acquired during startup would
        color a None icon and never show as connected.
        """
        if (
            event.new is None
            or not self._pygame_enabled
            or self._pygame_joystick is None
        ):
            return
        try:
            name = self._pygame_joystick.get_name()
        except Exception:
            name = "controller"
        self._set_gamepad_indicator(name)

    def _env_int(self, key: str, default: int | None) -> int | None:
        val = os.environ.get(key, "").strip()
        if val == "":
            return default
        try:
            return int(val)
        except Exception:
            logger.warning(f"Invalid int for {key}={val!r}")
            return default

    def _pref_int(self, env_key: str, pref_name: str, default: int) -> int:
        """Resolve an int gamepad setting: env var > stored preference > default.

        The env var keeps its historical override role; otherwise the value
        comes from the Device Viewer preferences (editable in the UI).
        """
        raw = os.environ.get(env_key, "").strip()
        if raw != "":
            try:
                return int(raw)
            except Exception:
                logger.warning(f"Invalid int for {env_key}={raw!r}")
        prefs = self.device_viewer_preferences
        if prefs is not None:
            try:
                return int(getattr(prefs, pref_name))
            except Exception:
                pass
        return default

    def _pref_float(self, env_key: str, pref_name: str, default: float) -> float:
        """Resolve a float gamepad setting: env var > stored preference > default."""
        raw = os.environ.get(env_key, "").strip()
        if raw != "":
            try:
                return float(raw)
            except Exception:
                logger.warning(f"Invalid float for {env_key}={raw!r}")
        prefs = self.device_viewer_preferences
        if prefs is not None:
            try:
                return float(getattr(prefs, pref_name))
            except Exception:
                pass
        return default

    def setup_pygame_gamepad_support(self) -> bool:
        """Enable gamepad input via pygame.

        Idempotent, so it is safe to call again when a new service instance is
        created on a model reload.

        NOTE: we must call the full ``pygame.init()`` (not just
        ``pygame.joystick.init()``). Joystick events are delivered through SDL's
        event queue, and on some platforms — notably macOS — that queue only
        works once the video/event subsystem is initialized and pumped. With
        only the joystick module initialized, ``pygame.event.get()`` returns no
        events and the controller appears completely unresponsive.

        The poll timer is started whenever pygame is up — even with no
        controller currently attached — so that ``JOYDEVICEADDED`` hot-plug
        events are received and a controller plugged in later still works.
        """
        if pygame is None:
            return False

        try:
            os.environ.setdefault("SDL_JOYSTICK_ALLOW_BACKGROUND_EVENTS", "1")
            # Guard so we don't re-init on every model reload. pygame.init() is
            # required for event delivery (see docstring); it is a no-op if the
            # relevant subsystems are already up.
            if not pygame.get_init():
                pygame.init()
            if not pygame.joystick.get_init():
                pygame.joystick.init()
        except Exception as e:
            logger.warning(f"pygame init failed: {e}")
            return False

        # Resolve the button mapping up front (env-based, controller-independent)
        # so it's ready the moment a controller is acquired.
        self._load_gamepad_mapping()

        # Grab a controller now if one is already present; otherwise the timer
        # below keeps polling so a JOYDEVICEADDED event can grab one later.
        self._acquire_joystick()
        self._start_pygame_timer()

        logger.info(
            "pygame gamepad support enabled (controller %s). Mapping: A=clear, "
            "Select=find, B=split, Y=add, X=remove, Start=realtime. Override with "
            "env vars MICRODROP_GAMEPAD_BTN_CLEAR / _BTN_FIND / _BTN_SPLIT / "
            "_BTN_ADD_MOD / _BTN_REMOVE_MOD / _BTN_REALTIME_TOGGLE.",
            "attached" if self._pygame_enabled else "waiting for hot-plug",
        )
        return True

    def _load_gamepad_mapping(self) -> None:
        """Load the (controller-independent) button mapping.

        Each value resolves as: MICRODROP_GAMEPAD_* env var > stored Device
        Viewer preference > built-in default. Re-run live whenever the
        preferences change (see _on_gamepad_buttons_pref_changed).

        For the common "USB gamepad" NES/SNES-style controller (per probe output):
          X=0, A=1, B=2, Y=3, L=4, R=5, Select=8, Start=9
        """
        for pref_name, env_key, attr, default in self._GAMEPAD_ACTIONS.values():
            setattr(self, attr, self._pref_int(env_key, pref_name, default))

    def _load_gamepad_timing(self) -> None:
        """Load debounce timings + analog-stick threshold.

        Same resolution order as the button mapping (env > preference >
        default). Re-run live on preference changes; no controller required.
        """
        self._dpad_debounce_move_split_s = self._pref_float(
            "MICRODROP_GAMEPAD_DPAD_DEBOUNCE_S",
            "gamepad_debounce_move_split",
            GAMEPAD_DEBOUNCE_MOVE_SPLIT_S,
        )
        self._dpad_debounce_add_remove_s = self._pref_float(
            "MICRODROP_GAMEPAD_DPAD_DEBOUNCE_ADD_REMOVE_S",
            "gamepad_debounce_add_remove",
            GAMEPAD_DEBOUNCE_ADD_REMOVE_S,
        )
        self._btn_debounce_find_liquid_s = self._pref_float(
            "MICRODROP_GAMEPAD_DEBOUNCE_FIND_S",
            "gamepad_debounce_find",
            GAMEPAD_DEBOUNCE_FIND_S,
        )
        self._btn_debounce_realtime_s = self._pref_float(
            "MICRODROP_GAMEPAD_DEBOUNCE_REALTIME_S",
            "gamepad_debounce_realtime",
            GAMEPAD_DEBOUNCE_REALTIME_S,
        )
        self._pygame_axis_threshold = self._pref_float(
            "MICRODROP_GAMEPAD_AXIS_THRESHOLD",
            "gamepad_axis_threshold",
            GAMEPAD_AXIS_THRESHOLD,
        )

    def _configure_dpad_mapping(self, js) -> None:
        """Resolve D-pad axis mapping for ``js``: prefer HAT, fall back to axes.

        The D-pad axis indices stay env-only (device-specific, not user-facing);
        the activation threshold lives in _load_gamepad_timing.
        """
        default_dpad_x = None
        default_dpad_y = None
        try:
            # Many cheap USB pads expose the D-pad as axes 0/1 instead of a hat.
            if js.get_numhats() == 0 and js.get_numaxes() >= 2:
                default_dpad_x = 0
                default_dpad_y = 1
        except Exception:
            pass

        self._pygame_dpad_x_axis = self._env_int(
            "MICRODROP_GAMEPAD_DPAD_X_AXIS", default_dpad_x
        )
        self._pygame_dpad_y_axis = self._env_int(
            "MICRODROP_GAMEPAD_DPAD_Y_AXIS", default_dpad_y
        )

    def _acquire_joystick(self) -> bool:
        """Grab joystick[0] if one is present. Safe to call repeatedly.

        Called both at setup and on a ``JOYDEVICEADDED`` hot-plug event. A no-op
        if a live joystick is already held or none is connected.
        """
        if pygame is None:
            return False
        try:
            count = pygame.joystick.get_count()
        except Exception:
            count = 0
        if count <= 0:
            self._pygame_enabled = False
            return False

        # Already holding a live controller?
        if self._pygame_joystick is not None:
            try:
                if self._pygame_joystick.get_init():
                    self._pygame_enabled = True
                    return True
            except Exception:
                pass

        try:
            js = pygame.joystick.Joystick(0)
            js.init()
            self._pygame_joystick = js
            self._pygame_enabled = True
            logger.info(f"pygame: using joystick[0]={js.get_name()!r}")
        except Exception as e:
            logger.warning(f"pygame: failed to acquire joystick: {e}")
            self._pygame_joystick = None
            self._pygame_enabled = False
            return False

        # D-pad defaults depend on the specific device.
        self._configure_dpad_mapping(js)
        try:
            name = js.get_name()
        except Exception:
            name = "controller"
        # Connection state is shown by the persistent status-bar joystick icon
        # (green + controller-name tooltip); no transient HUD message needed.
        self._set_gamepad_indicator(name)
        return True

    def _release_joystick(self) -> None:
        """Drop the current controller and reset any held input state.

        Called on a ``JOYDEVICEREMOVED`` hot-plug event and from ``cleanup``.
        Leaves the poll timer running so a reconnect can be picked up.
        """
        js = self._pygame_joystick
        self._pygame_joystick = None
        self._pygame_enabled = False
        self._set_gamepad_indicator("")

        # Clear held modifiers / split session so a reconnect starts clean and
        # we don't act on stale "button held" state from the removed device.
        self._split_modifier_down = False
        self._add_modifier_down = False
        self._remove_modifier_down = False
        self.stepping.reset_split_state()
        self._axis_left_pressed = False
        self._axis_right_pressed = False
        self._axis_up_pressed = False
        self._axis_down_pressed = False

        if js is not None:
            try:
                js.quit()
            except Exception:
                pass

    def _start_pygame_timer(self) -> None:
        """Start the gamepad poll timer (idempotent).

        The timer is parented to the device view (a QObject) so Qt bounds its
        lifetime and tears it down even if ``cleanup`` is somehow missed —
        preventing orphaned timers from stacking across model reloads.
        """
        if self._pygame_timer is not None:
            return  # already running
        timer = QTimer(self.device_view)
        timer.timeout.connect(self._poll_pygame_events)
        timer.start()
        self._pygame_timer = timer
        self._update_pygame_timer_interval()

    def _update_pygame_timer_interval(self) -> None:
        """~100 Hz while a controller is attached; a slow hot-plug-detection
        tick while none is (a persistent 100 Hz GUI-thread wakeup for an
        absent gamepad costs smoothness for nothing)."""
        if self._pygame_timer is None:
            return
        interval = (
            GAMEPAD_POLL_INTERVAL_MS
            if self._pygame_enabled
            else GAMEPAD_IDLE_POLL_INTERVAL_MS
        )
        if self._pygame_timer.interval() != interval:
            self._pygame_timer.setInterval(interval)

    # ------------------ Live remap (button capture) ------------------

    #: How long a pending capture request waits for a button press (seconds).
    _CAPTURE_TIMEOUT_S = 10.0

    def begin_button_capture(self, action: str) -> None:
        """Arm capture mode: the next button press binds to ``action``.

        Called (via the device-viewer listener) when the user clicks a "Rebind"
        button in the Gamepad preferences pane.
        """
        action = (action or "").strip()
        if action not in self._GAMEPAD_ACTIONS:
            logger.warning(f"gamepad capture: unknown action {action!r}")
            return
        if not self._pygame_enabled:
            logger.info(f"gamepad capture: no controller attached, ignoring {action!r}")
            return
        self._capture_action = action
        self._capture_deadline = time.monotonic() + self._CAPTURE_TIMEOUT_S
        self._set_hud(f"Gamepad: press a button to assign to '{action}'…")
        logger.info(f"gamepad capture armed for action {action!r}")

    def _finish_button_capture(self, btn: int) -> None:
        """Bind the captured ``btn`` to the pending action and persist it."""
        action, self._capture_action = self._capture_action, ""
        mapping = self._GAMEPAD_ACTIONS.get(action)
        if mapping is None:
            return
        pref_name, _env_key, _attr, _default = mapping

        # Warn (but don't block) if this button is already bound elsewhere — the
        # two handlers would both fire on that press. Up to the user to resolve.
        clashes = [
            other
            for other, m in self._GAMEPAD_ACTIONS.items()
            if other != action and getattr(self, m[2], None) == int(btn)
        ]
        if clashes:
            logger.warning(
                f"gamepad capture: button {btn} also bound to {', '.join(clashes)}"
            )

        prefs = self.device_viewer_preferences
        if prefs is not None:
            try:
                # Writing the preference persists it and syncs to the prefs pane
                # (clearing its capture prompt). Our own _on_gamepad_buttons_pref
                # observer then reloads the live mapping.
                setattr(prefs, pref_name, int(btn))
            except Exception as e:
                logger.warning(
                    f"gamepad capture: failed to store {pref_name}={btn}: {e}"
                )
        # Reload now too, in case no preferences object is wired up.
        self._load_gamepad_mapping()
        self._set_hud(f"Gamepad: '{action}' bound to button {btn}")
        logger.info(f"gamepad capture: action {action!r} -> button {btn}")

    def reconnect_gamepad(self) -> None:
        """Manually re-attempt controller acquisition (UI 'reconnect' action).

        Hot-plug is handled automatically via JOYDEVICEADDED, but this gives the
        user an explicit retry (e.g. if SDL missed the event). Re-inits the
        joystick subsystem so a freshly re-plugged device is enumerated.
        """
        if pygame is None:
            logger.warning("gamepad reconnect: pygame unavailable")
            return
        try:
            # Re-init the joystick subsystem so get_count() re-enumerates devices.
            pygame.joystick.quit()
            pygame.joystick.init()
        except Exception as e:
            logger.warning(f"gamepad reconnect: subsystem re-init failed: {e}")
        # Drop any stale handle, ensure the poll timer is running, then re-grab.
        self._release_joystick()
        self._start_pygame_timer()
        if self._acquire_joystick():
            logger.info("gamepad reconnect: controller acquired")
        else:
            logger.info("gamepad reconnect: no controller found")

    # ------------------ Live preference reload ------------------

    @observe(
        "device_viewer_preferences:gamepad_btn_clear,"
        "device_viewer_preferences:gamepad_btn_find,"
        "device_viewer_preferences:gamepad_btn_split,"
        "device_viewer_preferences:gamepad_btn_add,"
        "device_viewer_preferences:gamepad_btn_remove,"
        "device_viewer_preferences:gamepad_btn_realtime"
    )
    def _on_gamepad_buttons_pref_changed(self, event):
        self._load_gamepad_mapping()

    @observe(
        "device_viewer_preferences:gamepad_debounce_move_split,"
        "device_viewer_preferences:gamepad_debounce_add_remove,"
        "device_viewer_preferences:gamepad_debounce_find,"
        "device_viewer_preferences:gamepad_debounce_realtime,"
        "device_viewer_preferences:gamepad_axis_threshold"
    )
    def _on_gamepad_timing_pref_changed(self, event):
        self._load_gamepad_timing()

    def _poll_pygame_events(self) -> None:
        # Note: we keep polling even when no controller is attached
        # (``_pygame_enabled`` is False) so that JOYDEVICEADDED hot-plug events
        # are still received. We only bail if the subsystem itself is gone.
        if pygame is None or not pygame.joystick.get_init():
            return

        try:
            events = pygame.event.get()
        except Exception:
            try:
                pygame.event.pump()
            except Exception:
                return
            return

        # Expire a pending button-capture request that was never satisfied.
        if self._capture_action and time.monotonic() > self._capture_deadline:
            cancelled, self._capture_action = self._capture_action, ""
            self._set_hud(f"Gamepad: rebind of '{cancelled}' cancelled (timeout)")

        # Keep modifier state in sync even if button events are missed/reordered.
        # Only meaningful while a controller is live. Skipped during a pending
        # capture so pressing a modifier button to rebind it doesn't also flip
        # the live modifier / reset the split session as a side effect.
        if self._pygame_enabled and not self._capture_action:
            self._sync_modifiers_from_pygame_state()

        for e in events:
            et = getattr(e, "type", None)

            # --- Hot-plug: handled regardless of current attached state ---
            if et == getattr(pygame, "JOYDEVICEADDED", None):
                if not self._pygame_enabled:
                    self._acquire_joystick()
                continue
            if et == getattr(pygame, "JOYDEVICEREMOVED", None):
                if self._pygame_enabled:
                    # The joystick icon grays out + tooltips "Gamepad
                    # disconnected"; no transient HUD message needed.
                    self._release_joystick()
                continue

            # --- Input events: ignored unless a controller is attached ---
            if not self._pygame_enabled:
                continue

            if et == getattr(pygame, "JOYBUTTONDOWN", None):
                btn = int(getattr(e, "button", -1))
                self._handle_pygame_button(btn, pressed=True)
            elif et == getattr(pygame, "JOYBUTTONUP", None):
                btn = int(getattr(e, "button", -1))
                self._handle_pygame_button(btn, pressed=False)
            elif et == getattr(pygame, "JOYHATMOTION", None):
                value = getattr(e, "value", (0, 0))
                self._handle_pygame_hat(value)
            elif et == getattr(pygame, "JOYAXISMOTION", None):
                axis = int(getattr(e, "axis", -1))
                value = float(getattr(e, "value", 0.0))
                self._handle_pygame_axis(axis, value)

        # Hot-plug events above may have attached/released the controller:
        # follow with the matching poll cadence.
        self._update_pygame_timer_interval()

    def _sync_modifiers_from_pygame_state(self) -> None:
        """
        Read live joystick state for modifier buttons (X/Y/B holds).
        This avoids cases where SDL event ordering causes held modifiers to be missed.
        """
        js = self._pygame_joystick
        if pygame is None or js is None:
            return

        try:
            # Ensure joystick state is fresh.
            pygame.event.pump()
        except Exception:
            pass

        def _pressed(idx: int | None) -> bool:
            if idx is None:
                return False
            try:
                return bool(js.get_button(int(idx)))
            except Exception:
                return False

        new_split = _pressed(self._btn_split)
        new_add = _pressed(self._btn_add_modifier)
        new_remove = _pressed(self._btn_remove_modifier)

        # Rising edge of the split button starts a fresh split session.
        if new_split and not self._split_modifier_down:
            self.stepping.reset_split_state()
            self._axis_left_pressed = False
            self._axis_right_pressed = False
            self._axis_up_pressed = False
            self._axis_down_pressed = False

        # Falling edge ends the split session.
        if (not new_split) and self._split_modifier_down:
            self.stepping.reset_split_state()

        self._split_modifier_down = new_split
        self._add_modifier_down = new_add
        self._remove_modifier_down = new_remove

    def _handle_pygame_button(self, btn: int, pressed: bool) -> None:
        # Debug log: helps discover mapping quickly.
        if pressed:
            logger.debug(f"pygame button down: {btn}")

        # Live remap: if a capture is pending, the next press binds the button
        # to that action instead of performing its normal function.
        if self._capture_action and pressed:
            self._finish_button_capture(btn)
            return

        # A = clear all electrodes
        if btn == self._btn_clear and pressed:
            self.model.electrodes.clear_electrode_states()
            self.stepping.reset_split_state()
            self._set_hud("Cleared all electrodes")
            return

        # Select = find liquid (debounced, with temporary freq/voltage)
        if btn == self._btn_find_liquid and pressed:
            now = time.monotonic()
            if now - self._last_find_liquid_ts < self._btn_debounce_find_liquid_s:
                logger.debug("find-liquid debounced")
                return
            self._last_find_liquid_ts = now
            self.model.electrodes.clear_electrode_states()
            self.stepping.reset_split_state()
            publish_message(
                topic=DETECT_DROPLETS,
                message=json.dumps(
                    list(self.model.electrodes.channels_electrode_ids_map.keys())
                ),
            )
            return

        # Hold modifiers (B=split, Y=add, X=remove) are intentionally NOT
        # handled here. They are tracked from live device state in
        # _sync_modifiers_from_pygame_state (the single source of truth), which
        # runs every poll tick and on every direction event — so it can't drift
        # if SDL drops or reorders button up/down events. Just ignore them here.
        if btn in (self._btn_split, self._btn_add_modifier, self._btn_remove_modifier):
            return

        # Start = toggle realtime mode (debounced)
        if btn == self._btn_realtime_toggle and pressed:
            now = time.monotonic()
            if now - self._last_realtime_toggle_ts < self._btn_debounce_realtime_s:
                logger.debug("realtime-toggle debounced")
                return
            self._last_realtime_toggle_ts = now
            self._toggle_realtime_mode()
            return

    def _handle_pygame_hat(self, value: tuple[int, int]) -> None:
        x, y = value
        # SDL hat: (1,0)=right, (-1,0)=left, (0,1)=up, (0,-1)=down
        if x == -1:
            self._on_gamepad_direction("left")
        elif x == 1:
            self._on_gamepad_direction("right")
        elif y == 1:
            self._on_gamepad_direction("up")
        elif y == -1:
            self._on_gamepad_direction("down")

    def _handle_pygame_axis(self, axis: int, value: float) -> None:
        thr = float(self._pygame_axis_threshold or 0.6)

        if self._pygame_dpad_x_axis is not None and axis == int(
            self._pygame_dpad_x_axis
        ):
            left_now = value < -thr
            right_now = value > thr
            if left_now and not self._axis_left_pressed:
                self._on_gamepad_direction("left")
            if right_now and not self._axis_right_pressed:
                self._on_gamepad_direction("right")
            self._axis_left_pressed = left_now
            self._axis_right_pressed = right_now

        if self._pygame_dpad_y_axis is not None and axis == int(
            self._pygame_dpad_y_axis
        ):
            up_now = value < -thr
            down_now = value > thr
            if up_now and not self._axis_up_pressed:
                self._on_gamepad_direction("up")
            if down_now and not self._axis_down_pressed:
                self._on_gamepad_direction("down")
            self._axis_up_pressed = up_now
            self._axis_down_pressed = down_now

    def _on_gamepad_direction(self, direction: str) -> None:
        # Make sure modifier state reflects current joystick holds.
        self._sync_modifiers_from_pygame_state()
        mapped_direction = self.stepping.map_direction_for_device_rotation(direction)

        now = time.monotonic()
        if self._add_modifier_down or self._remove_modifier_down:
            debounce_s = float(getattr(self, "_dpad_debounce_add_remove_s", 0.3) or 0.0)
        else:
            debounce_s = float(getattr(self, "_dpad_debounce_move_split_s", 0.7) or 0.0)
        if (
            debounce_s > 0
            and (now - float(getattr(self, "_last_dpad_action_ts", 0.0))) < debounce_s
        ):
            mode = (
                "SPLIT"
                if self._split_modifier_down
                else (
                    "ADD"
                    if self._add_modifier_down
                    else ("REMOVE" if self._remove_modifier_down else "MOVE")
                )
            )
            self._set_hud(
                f"Pad: {mode} {direction}->{mapped_direction} "
                f"(debounce {debounce_s:.0f}s)"
            )
            return
        self._last_dpad_action_ts = now

        mode = (
            "SPLIT"
            if self._split_modifier_down
            else (
                "ADD"
                if self._add_modifier_down
                else ("REMOVE" if self._remove_modifier_down else "MOVE")
            )
        )
        axis = "H" if mapped_direction in ("left", "right") else "V"
        active_n = len(self.stepping.get_active_electrode_ids())
        self._set_hud(
            f"Pad: {mode} {direction}->{mapped_direction} axis={axis} active={active_n}"
        )

        if os.environ.get("MICRODROP_GAMEPAD_DEBUG", "").strip() == "1":
            logger.info(
                "gamepad dir=%s mapped=%s rot=%d x=%s add=%s remove=%s active=%d",
                direction,
                mapped_direction,
                self.model.device_rotation_deg,
                self._split_modifier_down,
                self._add_modifier_down,
                self._remove_modifier_down,
                len(self.stepping.get_active_electrode_ids()),
            )

        if self._split_modifier_down:
            self.stepping.split_step(mapped_direction)
        elif self._add_modifier_down:
            self.stepping.extend_active_electrodes(mapped_direction)
        elif self._remove_modifier_down:
            self.stepping.shrink_active_electrodes(mapped_direction)
        else:
            self.stepping.step_active_electrodes(mapped_direction)

    def _toggle_realtime_mode(self) -> None:
        """Request a realtime-mode toggle via the Start button.

        The desired state is derived from the shared model (kept in sync by
        REALTIME_MODE_UPDATED) rather than a private mirror, so the gamepad
        can't drift out of sync with the mouse-driven checkbox. The HUD is
        updated by ``_on_model_realtime_mode_changed`` once the change is
        actually applied, not optimistically here.
        """
        if not bool(getattr(self.model, "connected", False)):
            # on_set_realtime_mode_request only runs when the DropBot is
            # connected; publishing now would silently do nothing.
            self._set_hud("Realtime mode: connect DropBot first")
            logger.info("Gamepad: realtime toggle ignored (DropBot not connected)")
            return

        desired = not bool(getattr(self.model, "realtime_mode", False))
        publish_message(topic=SET_REALTIME_MODE, message=str(desired))
        logger.info(f"Gamepad: realtime mode toggle requested -> {desired}")

    @observe("model:realtime_mode")
    def _on_model_realtime_mode_changed(self, event) -> None:
        """Reflect the applied realtime-mode state on the HUD."""
        state_str = "ON" if bool(event.new) else "OFF"
        self._set_hud(f"Realtime mode: {state_str}")

    @observe("model:device_rotation_deg")
    def _on_device_rotation_changed(self, event) -> None:
        """Reflect the device orientation the pad directions now follow."""
        self._set_hud(f"Device orientation: {event.new} deg")

    def cleanup(self) -> None:
        """Disconnect controller listeners on model reloads.

        Stops and disposes the poll timer and releases the controller. The
        pygame joystick *subsystem* is intentionally left initialized: a fresh
        service re-runs ``setup_pygame_gamepad_support`` (which is idempotent),
        so quitting/re-initializing SDL on every reload would just be churn.
        """
        try:
            if self._pygame_timer is not None:
                try:
                    self._pygame_timer.stop()
                    # Parented to the device view; deleteLater lets Qt reclaim it.
                    self._pygame_timer.deleteLater()
                except Exception:
                    pass
                self._pygame_timer = None
            # Releases the controller and clears held modifier/split state.
            self._release_joystick()
        finally:
            # Remove HUD message
            try:
                if self._hud_message and getattr(self, "status_bar_manager", None):
                    self.status_bar_manager.remove(self._hud_message)
            except Exception:
                pass
            self._hud_message = ""
