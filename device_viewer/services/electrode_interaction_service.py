import os
import json
import time

from PySide6.QtGui import QKeyEvent, Qt, QWheelEvent, QAction
from PySide6.QtWidgets import (QGraphicsView, QGraphicsSceneWheelEvent, 
                               QGraphicsSceneContextMenuEvent, QMenu)
from traits.api import HasTraits, Instance, Dict, List, Str, observe, Bool, Float
from PySide6.QtCore import QPointF, QTimer

try:
    import pygame  
except Exception:  
    pygame = None

from device_viewer.models.electrodes import Electrode
from device_viewer.utils.electrode_route_helpers import find_shortest_paths
from dropbot_controller.consts import (
    DETECT_DROPLETS, SET_REALTIME_MODE
)
from device_viewer.consts import (
    GAMEPAD_BTN_CLEAR, GAMEPAD_BTN_FIND, GAMEPAD_BTN_SPLIT, GAMEPAD_BTN_ADD,
    GAMEPAD_BTN_REMOVE, GAMEPAD_BTN_REALTIME, GAMEPAD_DEBOUNCE_MOVE_SPLIT_S,
    GAMEPAD_DEBOUNCE_ADD_REMOVE_S, GAMEPAD_DEBOUNCE_FIND_S,
    GAMEPAD_DEBOUNCE_REALTIME_S, GAMEPAD_AXIS_THRESHOLD,
    GAMEPAD_POLL_INTERVAL_MS, GAMEPAD_IDLE_POLL_INTERVAL_MS,
)
from logger.logger_service import get_logger
from microdrop_style.colors import GREY, SUCCESS_COLOR
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.models.route import Route, RouteLayer
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.electrode_view.electrodes_view_base import ElectrodeView, ElectrodeConnectionItem, \
    ElectrodeEndpointItem
from device_viewer.default_settings import AUTOROUTE_COLOR, electrode_outline_key, \
    electrode_fill_key, actuated_electrodes_key, electrode_text_key, routes_key, connections_key
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from ..preferences import DeviceViewerPreferences
from ..views.electrode_view.electrode_view_helpers import find_path_item
from ..views.electrode_view.scale_edit_view import ScaleEditViewController

logger = get_logger(__name__)

# Sentinel returned by channel-text parsing when the edit should be reverted
# (kept distinct from None, which means "unassign the channel").
_CHANNEL_REVERT = object()

class ElectrodeInteractionControllerService(HasTraits):
    """Service to handle electrode interactions. Converts complicated Qt-events into more application specific events.
    Note that this is not an Envisage or Pyface callback/handler class, and is only called manually from the ElectrodeScene class.

    The following should be passed as kwargs to the constructor:
    - model: The main model instance.
    - electrode_view_layer: The current electrode layer view.
    - device_view: the current QGraphics device view
    - device_viewer_preferences: preferences for the current device viewer
    """

    #: Device view Model
    model = Instance(DeviceViewMainModel)

    #: The current electrode layer view
    electrode_view_layer = Instance(ElectrodeLayer)

    #: The current device view
    device_view = Instance(QGraphicsView)

    #: The preferences for the current device view
    device_viewer_preferences = Instance(DeviceViewerPreferences)

    #: Optional: status bar manager for HUD messages
    status_bar_manager = Instance(object, allow_none=True)

    #: Optional: persistent joystick indicator (QLabel) on the app status
    #: bar. Created and contributed by the device-viewer dock pane; this
    #: service only recolors it and sets its tooltip.
    gamepad_icon = Instance(object, allow_none=True)

    autoroute_paths = Dict({})

    electrode_hovered = Instance(ElectrodeView)

    rect_editing_index = -1  # Index of the point being edited in the reference rect
    rect_buffer = List(Instance(QPointF), [])

    #: state data fields
    _last_electrode_id_visited = Str(allow_none=True, desc="The last electrode clicked / dragged on by user's id.")

    _left_mouse_pressed = Bool(False)
    _right_mouse_pressed = Bool(False)

    _edit_reference_rect = Bool(False, desc='Is the reference rect editable without affecting perpective.')

    _electrode_tooltip_visible = Bool(True)

    _is_drag = Bool(False, desc='Is user dragging the pointer on screen')

    _split_modifier_down = Bool(False, desc="When True (B held), arrow presses are split steps.")
    _add_modifier_down = Bool(False, desc="When True (Y held), arrows extend active electrodes.")
    _remove_modifier_down = Bool(False, desc="When True (X held), arrows shrink active electrodes.")
    # NOTE: Traits `Str` does not accept None reliably; use "" as the unset sentinel.
    _split_axis = Str("", desc="Split axis: 'h' or 'v'. Empty means unset.")
    _split_arm_neg = Str("", desc="Negative-direction split arm electrode id. Empty means unset.")
    _split_arm_pos = Str("", desc="Positive-direction split arm electrode id. Empty means unset.")

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
        "clear":    ("gamepad_btn_clear",    "MICRODROP_GAMEPAD_BTN_CLEAR",           "_btn_clear",           GAMEPAD_BTN_CLEAR),
        "find":     ("gamepad_btn_find",     "MICRODROP_GAMEPAD_BTN_FIND",            "_btn_find_liquid",     GAMEPAD_BTN_FIND),
        "split":    ("gamepad_btn_split",    "MICRODROP_GAMEPAD_BTN_SPLIT",           "_btn_split",           GAMEPAD_BTN_SPLIT),
        "add":      ("gamepad_btn_add",      "MICRODROP_GAMEPAD_BTN_ADD_MOD",         "_btn_add_modifier",    GAMEPAD_BTN_ADD),
        "remove":   ("gamepad_btn_remove",   "MICRODROP_GAMEPAD_BTN_REMOVE_MOD",      "_btn_remove_modifier", GAMEPAD_BTN_REMOVE),
        "realtime": ("gamepad_btn_realtime", "MICRODROP_GAMEPAD_BTN_REALTIME_TOGGLE", "_btn_realtime_toggle", GAMEPAD_BTN_REALTIME),
    }

    _hud_message = Str("")

    #######################################################################################################
    # Helpers
    #######################################################################################################

    def traits_init(self):
        # Split-mode history (for contracting back toward the mirror point).
        self._split_sessions: list[dict] = []
        self._split_base_ids: set[str] | None = None

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
        # Cumulative device-view rotation is stored on the model as
        # model.device_rotation_deg (persisted via preferences). Apply any
        # rotation loaded from preferences to the view now that both the
        # QGraphicsView and the electrode layer are bound.
        self._apply_persisted_device_rotation()

    def _apply_persisted_device_rotation(self) -> None:
        """Apply the persisted rotation angle to the QGraphicsView.

        Mirrors the sequence used by `_rotate_device_view` (rotate the
        view, counter-rotate label text, then re-fit) so the loaded state
        looks identical to what a user-driven rotate would produce.
        """
        rot = int(self.model.device_rotation_deg or 0) % 360
        if not rot:
            return
        self.device_view.rotate(rot)
        self.electrode_view_layer.rotate_electrode_views_texts(-rot)
        self.device_view.fit_to_scene_rect()

    def _set_hud(self, text: str) -> None:
        mgr = getattr(self, "status_bar_manager", None)
        if mgr is None:
            return
        try:
            # Remove the previous HUD message if present.
            if self._hud_message:
                try:
                    mgr.remove(self._hud_message)
                except Exception:
                    try:
                        mgr.messages = [m for m in mgr.messages if m != self._hud_message]
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
        except RuntimeError as e:       # icon deleted with the window
            logger.debug(f"gamepad indicator gone: {e}")

    @observe("gamepad_icon")
    def _on_gamepad_icon_set(self, event):
        """Re-apply the connection state when the joystick icon arrives.

        The icon is None when this service is constructed (the dock pane
        creates and contributes it once the status bar exists) and is pushed
        in later. Without this, a controller acquired during startup would
        color a None icon and never show as connected.
        """
        if event.new is None or not self._pygame_enabled or self._pygame_joystick is None:
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
            "MICRODROP_GAMEPAD_DPAD_DEBOUNCE_S", "gamepad_debounce_move_split", GAMEPAD_DEBOUNCE_MOVE_SPLIT_S)
        self._dpad_debounce_add_remove_s = self._pref_float(
            "MICRODROP_GAMEPAD_DPAD_DEBOUNCE_ADD_REMOVE_S", "gamepad_debounce_add_remove", GAMEPAD_DEBOUNCE_ADD_REMOVE_S)
        self._btn_debounce_find_liquid_s = self._pref_float(
            "MICRODROP_GAMEPAD_DEBOUNCE_FIND_S", "gamepad_debounce_find", GAMEPAD_DEBOUNCE_FIND_S)
        self._btn_debounce_realtime_s = self._pref_float(
            "MICRODROP_GAMEPAD_DEBOUNCE_REALTIME_S", "gamepad_debounce_realtime", GAMEPAD_DEBOUNCE_REALTIME_S)
        self._pygame_axis_threshold = self._pref_float(
            "MICRODROP_GAMEPAD_AXIS_THRESHOLD", "gamepad_axis_threshold", GAMEPAD_AXIS_THRESHOLD)

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

        self._pygame_dpad_x_axis = self._env_int("MICRODROP_GAMEPAD_DPAD_X_AXIS", default_dpad_x)
        self._pygame_dpad_y_axis = self._env_int("MICRODROP_GAMEPAD_DPAD_Y_AXIS", default_dpad_y)

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
        self._reset_split_state()
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
        interval = (GAMEPAD_POLL_INTERVAL_MS if self._pygame_enabled
                    else GAMEPAD_IDLE_POLL_INTERVAL_MS)
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
            self._set_hud("Gamepad: connect a controller before rebinding")
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
            other for other, m in self._GAMEPAD_ACTIONS.items()
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
                logger.warning(f"gamepad capture: failed to store {pref_name}={btn}: {e}")
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
            self._set_hud("Gamepad: pygame unavailable")
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
            self._set_hud("Gamepad: no controller found")
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
            self._reset_split_state()
            self._axis_left_pressed = False
            self._axis_right_pressed = False
            self._axis_up_pressed = False
            self._axis_down_pressed = False

        # Falling edge ends the split session.
        if (not new_split) and self._split_modifier_down:
            self._reset_split_state()

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
            self._reset_split_state()
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
            self._reset_split_state()
            self.detect_droplet()
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

        if self._pygame_dpad_x_axis is not None and axis == int(self._pygame_dpad_x_axis):
            left_now = value < -thr
            right_now = value > thr
            if left_now and not self._axis_left_pressed:
                self._on_gamepad_direction("left")
            if right_now and not self._axis_right_pressed:
                self._on_gamepad_direction("right")
            self._axis_left_pressed = left_now
            self._axis_right_pressed = right_now

        if self._pygame_dpad_y_axis is not None and axis == int(self._pygame_dpad_y_axis):
            up_now = value < -thr
            down_now = value > thr
            if up_now and not self._axis_up_pressed:
                self._on_gamepad_direction("up")
            if down_now and not self._axis_down_pressed:
                self._on_gamepad_direction("down")
            self._axis_up_pressed = up_now
            self._axis_down_pressed = down_now

    def _get_device_rotation_deg(self) -> int:
        """Return tracked device-view rotation (0/90/180/270)."""
        return int(self.model.device_rotation_deg or 0) % 360

    def _map_direction_for_device_rotation(self, direction: str) -> str:
        """
        Map an input direction (controller/keyboard) to the device-frame direction
        based on the current view rotation.

        Example: if view is rotated +90 deg, pressing "up" should move visually up,
        which corresponds to device-frame "left".
        """
        if direction not in {"up", "right", "down", "left"}:
            return direction

        rotation_deg = self._get_device_rotation_deg()
        steps = (rotation_deg // 90) % 4
        dirs = ["up", "right", "down", "left"]
        idx = dirs.index(direction)
        return dirs[(idx - steps) % 4]

    def _on_gamepad_direction(self, direction: str) -> None:
        # Make sure modifier state reflects current joystick holds.
        self._sync_modifiers_from_pygame_state()
        mapped_direction = self._map_direction_for_device_rotation(direction)

        now = time.monotonic()
        if self._add_modifier_down or self._remove_modifier_down:
            debounce_s = float(getattr(self, "_dpad_debounce_add_remove_s", 0.3) or 0.0)
        else:
            debounce_s = float(getattr(self, "_dpad_debounce_move_split_s", 0.7) or 0.0)
        if debounce_s > 0 and (now - float(getattr(self, "_last_dpad_action_ts", 0.0))) < debounce_s:
            mode = "SPLIT" if self._split_modifier_down else ("ADD" if self._add_modifier_down else ("REMOVE" if self._remove_modifier_down else "MOVE"))
            self._set_hud(f"Pad: {mode} {direction}->{mapped_direction} (debounce {debounce_s:.0f}s)")
            return
        self._last_dpad_action_ts = now

        mode = "SPLIT" if self._split_modifier_down else ("ADD" if self._add_modifier_down else ("REMOVE" if self._remove_modifier_down else "MOVE"))
        axis = "H" if mapped_direction in ("left", "right") else "V"
        active_n = len(self._get_active_electrode_ids())
        self._set_hud(f"Pad: {mode} {direction}->{mapped_direction} axis={axis} active={active_n}")

        if os.environ.get("MICRODROP_GAMEPAD_DEBUG", "").strip() == "1":
            logger.info(
                "gamepad dir=%s mapped=%s rot=%d x=%s add=%s remove=%s active=%d",
                direction,
                mapped_direction,
                self._get_device_rotation_deg(),
                self._split_modifier_down,
                self._add_modifier_down,
                self._remove_modifier_down,
                len(self._get_active_electrode_ids()),
            )

        if self._split_modifier_down:
            self._split_step(mapped_direction)
        elif self._add_modifier_down:
            self._extend_active_electrodes(mapped_direction)
        elif self._remove_modifier_down:
            self._shrink_active_electrodes(mapped_direction)
        else:
            self._step_active_electrodes(mapped_direction)

    # ------------------ Electrode actuation helpers ------------------

    def _get_active_electrode_ids(self) -> set[str]:
        """
        Return electrode IDs implied by active channels.

        Note: channel -> electrode_ids is one-to-many, so this returns the union.
        """
        active_ids: set[str] = set()
        channels_map = self.model.electrodes.channels_electrode_ids_map or {}
        for ch in self.model.electrodes.actuated_channels:
            for electrode_id in channels_map.get(ch, []):
                active_ids.add(electrode_id)
        return active_ids

    def _apply_active_electrode_ids(self, desired_electrode_ids: set[str]) -> None:
        """
        Apply desired electrode IDs by mapping to channels and setting actuated_channels.
        """
        electrode_to_channel = self.model.electrodes.electrode_ids_channels_map or {}

        desired_channels: set[int] = set()
        for electrode_id in desired_electrode_ids:
            ch = electrode_to_channel.get(electrode_id, None)
            if ch is not None:
                desired_channels.add(int(ch))

        self.model.electrodes.actuated_channels = desired_channels

    def _direction_vec(self, direction: str) -> tuple[float, float]:
        # SVG coordinate system typically has +y downward.
        if direction == "left":
            return (-1.0, 0.0)
        if direction == "right":
            return (1.0, 0.0)
        if direction == "up":
            return (0.0, -1.0)
        if direction == "down":
            return (0.0, 1.0)
        raise ValueError(f"Unknown direction: {direction}")

    def _neighbor_in_direction(self, electrode_id: str, direction: str) -> str | None:
        """
        Pick the "best" neighbor in the requested direction using electrode centroid geometry.
        Returns None if no neighbor is reasonably in that direction.
        """
        svg = getattr(self.model.electrodes, "svg_model", None)
        if svg is None or not getattr(svg, "neighbours", None) or not getattr(svg, "electrode_centers", None):
            return None

        neighbors = svg.neighbours.get(electrode_id, []) or []
        if not neighbors:
            return None

        cx, cy = svg.electrode_centers.get(electrode_id, (None, None))
        if cx is None:
            return None

        dx, dy = self._direction_vec(direction)

        best_id = None
        best_score = None
        for nid in neighbors:
            nx, ny = svg.electrode_centers.get(nid, (None, None))
            if nx is None:
                continue
            vx = nx - cx
            vy = ny - cy
            # Prefer large projection in requested direction, penalize sideways motion a bit.
            proj = vx * dx + vy * dy
            if proj <= 0:
                continue
            perp = abs(vx * (-dy) + vy * dx)
            score = proj - 0.35 * perp
            if best_score is None or score > best_score:
                best_score = score
                best_id = nid

        return best_id

    def _step_active_electrodes(self, direction: str) -> None:
        if self.model.mode not in ("edit", "draw", "edit-draw", "merge"):
            return

        active_ids = self._get_active_electrode_ids()
        if not active_ids:
            # Fallback: if user hasn't actuated anything, try last visited.
            if self._last_electrode_id_visited:
                active_ids = {self._last_electrode_id_visited}
            else:
                return

        new_ids: set[str] = set()
        moved_any = False
        for eid in active_ids:
            nid = self._neighbor_in_direction(eid, direction)
            if nid is None:
                new_ids.add(eid)
            else:
                moved_any = True
                new_ids.add(nid)

        if moved_any:
            self._apply_active_electrode_ids(new_ids)
            # Update "current" electrode for subsequent steps.
            # Pick one of the moved electrodes (arbitrary but stable).
            self._last_electrode_id_visited = next(iter(new_ids))

    def _extend_active_electrodes(self, direction: str) -> None:
        """
        Extend active electrodes by adding one layer on the frontier in `direction`
        (A held + D-pad).
        """
        if self.model.mode not in ("edit", "draw", "edit-draw", "merge"):
            return

        active_ids = self._get_active_electrode_ids()
        if not active_ids:
            if self._last_electrode_id_visited:
                active_ids = {self._last_electrode_id_visited}
            else:
                return

        svg = getattr(self.model.electrodes, "svg_model", None)
        centers = getattr(svg, "electrode_centers", None) if svg else None
        if not centers:
            base = self._last_electrode_id_visited or next(iter(active_ids))
            nid = self._neighbor_in_direction(base, direction)
            if nid:
                desired = set(active_ids)
                desired.add(nid)
                self._apply_active_electrode_ids(desired)
                self._last_electrode_id_visited = nid
            return

        dx, dy = self._direction_vec(direction)
        projections: dict[str, float] = {}
        for eid in active_ids:
            cx, cy = centers.get(eid, (None, None))
            if cx is None:
                continue
            projections[eid] = cx * dx + cy * dy

        if not projections:
            return

        max_proj = max(projections.values())
        eps = 1e-6
        frontier = [eid for eid, p in projections.items() if (max_proj - p) <= eps]

        additions: set[str] = set()
        for eid in frontier:
            nid = self._neighbor_in_direction(eid, direction)
            if nid is not None:
                additions.add(nid)

        if additions:
            desired = set(active_ids) | additions
            self._apply_active_electrode_ids(desired)
            self._last_electrode_id_visited = next(iter(additions))

    def _shrink_active_electrodes(self, direction: str) -> None:
        """
        Shrink active electrodes by removing the "frontier" layer in `direction`
        (B held + D-pad).
        """
        if self.model.mode not in ("edit", "draw", "edit-draw", "merge"):
            return

        active_ids = self._get_active_electrode_ids()
        if not active_ids:
            return

        if len(active_ids) <= 1:
            # Can't shrink further—treat as clear.
            self.model.electrodes.clear_electrode_states()
            self._reset_split_state()
            return

        svg = getattr(self.model.electrodes, "svg_model", None)
        centers = getattr(svg, "electrode_centers", None) if svg else None
        if not centers:
            # No geometry; remove the last visited if active.
            if self._last_electrode_id_visited in active_ids and len(active_ids) > 1:
                desired = set(active_ids)
                desired.remove(self._last_electrode_id_visited)
                self._apply_active_electrode_ids(desired)
            return

        dx, dy = self._direction_vec(direction)
        projections: dict[str, float] = {}
        for eid in active_ids:
            cx, cy = centers.get(eid, (None, None))
            if cx is None:
                continue
            projections[eid] = cx * dx + cy * dy

        if not projections:
            return

        max_proj = max(projections.values())
        eps = 1e-6
        frontier = {eid for eid, p in projections.items() if (max_proj - p) <= eps}

        desired = set(active_ids) - frontier
        if not desired:
            self.model.electrodes.clear_electrode_states()
            self._reset_split_state()
            return

        self._apply_active_electrode_ids(desired)
        self._last_electrode_id_visited = next(iter(desired))

    def _reset_split_state(self) -> None:
        self._split_axis = ""
        self._split_arm_neg = ""
        self._split_arm_pos = ""
        try:
            self._split_sessions.clear()
        except Exception:
            self._split_sessions = []
        self._split_base_ids = None

    def _get_active_components(self, active_ids: set[str]) -> list[set[str]]:
        """
        Partition active electrode IDs into connected components using the SVG neighbour graph.
        Each component corresponds to an independent "droplet blob" for splitting.
        """
        if not active_ids:
            return []

        svg = getattr(self.model.electrodes, "svg_model", None)
        neighbours = getattr(svg, "neighbours", None) if svg else None
        if not neighbours:
            return [set(active_ids)]

        remaining = set(active_ids)
        components: list[set[str]] = []
        while remaining:
            start = next(iter(remaining))
            stack = [start]
            comp = {start}
            remaining.remove(start)
            while stack:
                cur = stack.pop()
                for nb in neighbours.get(cur, []) or []:
                    if nb in remaining:
                        remaining.remove(nb)
                        comp.add(nb)
                        stack.append(nb)
            components.append(comp)
        return components

    def _split_step(self, direction: str) -> None:
        """
        Split stepping while X is held.

        Behavior:
        - The first arrow press selects the split axis (left/right => horizontal, up/down => vertical)
          and starts a fresh split session (mirror point fixed for the duration of holding X).
        - Right/Down: move *further away* from the mirror point (expand).
        - Left/Up: move *closer* to the mirror point (contract).

        Each connected component of active electrodes is treated as an independent droplet blob.
        """
        if self.model.mode not in ("edit", "draw", "edit-draw", "merge"):
            return

        svg = getattr(self.model.electrodes, "svg_model", None)
        centers = getattr(svg, "electrode_centers", None) if svg else None

        # If nothing is active, split should do nothing and should not "remember" old state.
        active_now = self._get_active_electrode_ids()
        if not active_now:
            self._reset_split_state()
            return

        axis = "h" if direction in ("left", "right") else "v"
        expand = direction in ("right", "down")
        contract = direction in ("left", "up")

        # Initialize / re-initialize sessions when axis changes.
        if (self._split_axis or "") != axis:
            self._reset_split_state()
            self._split_axis = axis

            self._split_base_ids = set(active_now)
            self._split_sessions = []
            for comp in self._get_active_components(active_now):
                ids_list = list(comp)
                if not ids_list:
                    continue
                if centers:
                    if axis == "h":
                        ids_list.sort(key=lambda eid: centers.get(eid, (0.0, 0.0))[0])
                    else:
                        ids_list.sort(key=lambda eid: centers.get(eid, (0.0, 0.0))[1])
                n = len(ids_list)
                if n == 1:
                    left_ids = {ids_list[0]}
                    right_ids = {ids_list[0]}
                    mirror_ids: set[str] = set()
                else:
                    mid = n // 2
                    if n % 2 == 1:
                        mirror_ids = {ids_list[mid]}
                        left_ids = set(ids_list[:mid])
                        right_ids = set(ids_list[mid + 1 :])
                    else:
                        mirror_ids = set()
                        left_ids = set(ids_list[:mid])
                        right_ids = set(ids_list[mid:])
                self._split_sessions.append(
                    {
                        # Track two "groups" on either side of the mirror point.
                        "left_ids": left_ids,
                        "right_ids": right_ids,
                        "mirror_ids": mirror_ids,
                        "history": [],  # list[tuple[set[str], set[str]]]
                        "normalized": False,  # first expand: only remove middle (or split single)
                    }
                )

        neg_dir = "left" if axis == "h" else "up"
        pos_dir = "right" if axis == "h" else "down"

        # Helper: shift a set by one neighbor step in `direction`.
        def _shift(ids: set[str], direction: str) -> tuple[set[str], bool]:
            moved = False
            out: set[str] = set()
            for eid in ids:
                nid = self._neighbor_in_direction(eid, direction)
                if nid is None:
                    out.add(eid)
                else:
                    moved = True
                    out.add(nid)
            return out, moved

        if contract:
            desired_all: set[str] = set()
            any_change = False
            for sess in self._split_sessions:
                hist = sess.get("history") or []
                if hist:
                    prev_left, prev_right = hist.pop()
                    sess["left_ids"] = set(prev_left)
                    sess["right_ids"] = set(prev_right)
                    any_change = True
                desired_all |= set(sess.get("left_ids") or set())
                desired_all |= set(sess.get("right_ids") or set())
            if any_change and desired_all:
                self._apply_active_electrode_ids(desired_all)
                self._last_electrode_id_visited = next(iter(desired_all))
                return

            # Fully contracted: merge back to the original pre-split selection.
            if not any_change and self._split_base_ids:
                base_ids = set(self._split_base_ids)
                self._apply_active_electrode_ids(base_ids)
                self._last_electrode_id_visited = next(iter(base_ids))

                # Reinitialize sessions from the merged state so the next expand starts cleanly.
                self._split_sessions = []
                for comp in self._get_active_components(base_ids):
                    ids_list = list(comp)
                    if not ids_list:
                        continue
                    if centers:
                        if axis == "h":
                            ids_list.sort(
                                key=lambda eid: centers.get(eid, (0.0, 0.0))[0]
                            )
                        else:
                            ids_list.sort(
                                key=lambda eid: centers.get(eid, (0.0, 0.0))[1]
                            )
                    n = len(ids_list)
                    if n == 1:
                        left_ids = {ids_list[0]}
                        right_ids = {ids_list[0]}
                        mirror_ids: set[str] = set()
                    else:
                        mid = n // 2
                        if n % 2 == 1:
                            mirror_ids = {ids_list[mid]}
                            left_ids = set(ids_list[:mid])
                            right_ids = set(ids_list[mid + 1 :])
                        else:
                            mirror_ids = set()
                            left_ids = set(ids_list[:mid])
                            right_ids = set(ids_list[mid:])
                    self._split_sessions.append(
                        {
                            "left_ids": left_ids,
                            "right_ids": right_ids,
                            "mirror_ids": mirror_ids,
                            "history": [],
                            "normalized": False,
                        }
                    )
            return

        if not expand:
            return

        # First expand after starting split:
        # - If 3+ electrodes selected, only turn off the middle (mirror electrode) and keep the rest.
        # - If 1 electrode selected, perform the actual split into its two neighbors.
        # Subsequent expands: move left/right groups outward as groups.
        desired_all: set[str] = set()
        moved_any = False
        for sess in self._split_sessions:
            left_ids: set[str] = set(sess.get("left_ids") or set())
            right_ids: set[str] = set(sess.get("right_ids") or set())
            mirror_ids: set[str] = set(sess.get("mirror_ids") or set())

            if not sess.get("normalized", False):
                # Save current groups for contraction.
                try:
                    sess["history"].append((set(left_ids), set(right_ids)))
                except Exception:
                    pass

                if len(left_ids) == 1 and left_ids == right_ids and not mirror_ids:
                    # Single-electrode case: split into neighbors (both sides) immediately.
                    center = next(iter(left_ids))
                    new_left = self._neighbor_in_direction(center, neg_dir) or center
                    new_right = self._neighbor_in_direction(center, pos_dir) or center
                    left_ids = {new_left}
                    right_ids = {new_right}
                    sess["left_ids"] = left_ids
                    sess["right_ids"] = right_ids
                    sess["normalized"] = True
                    desired_all |= left_ids | right_ids
                    moved_any = True
                    continue

                # Multi-electrode case:
                # - Odd count: deactivate the single middle (mirror) and keep the rest.
                # - Even count: there is no single middle; immediately begin expanding outward.
                sess["normalized"] = True

                if mirror_ids:
                    desired_all |= left_ids | right_ids
                    moved_any = True
                    continue

                # Even-count: move ONLY the positive-side group on the first step.
                # This creates a *single* gap between the two sides (instead of two).
                new_right, moved_right = _shift(right_ids, pos_dir)
                sess["left_ids"] = left_ids
                sess["right_ids"] = new_right
                desired_all |= left_ids | new_right
                moved_any = moved_any or moved_right
                continue

            # Save current groups for contraction.
            try:
                sess["history"].append((set(left_ids), set(right_ids)))
            except Exception:
                pass

            # Expand away from mirror: left group moves neg_dir, right group moves pos_dir.
            new_left, moved_left = _shift(left_ids, neg_dir)
            new_right, moved_right = _shift(right_ids, pos_dir)
            moved_any = moved_any or moved_left or moved_right

            sess["left_ids"] = new_left
            sess["right_ids"] = new_right
            desired_all |= new_left | new_right

        if moved_any and desired_all:
            self._apply_active_electrode_ids(desired_all)
            self._last_electrode_id_visited = next(iter(desired_all))
        return

    # -----------------------------------------------------------------
    # Realtime-mode toggle (Start button)
    # -----------------------------------------------------------------
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

    def _zoom_in(self, scale=None):
        logger.debug("Zoom In")
        # disable auto fit if user wants to zoom in
        if self.device_view.auto_fit:
            self.device_view.auto_fit = False

        if scale is None:
            scale = self.device_viewer_preferences._zoom_scale

        self.device_view.scale(scale, scale)

    def _zoom_out(self, scale=None):
        logger.debug("Zoom Out")

        if scale is None:
            scale = self.device_viewer_preferences._zoom_scale

        self.device_view.scale(1 / scale, 1 / scale)

    def _rotate_device_view(self, angle_step):

        # enable auto fit for rotations:
        if not self.device_view.auto_fit:
            self.device_view.auto_fit = True

        # rotate entire view:
        self.device_view.rotate(angle_step)

        # Track cumulative device-view rotation to remap controller directions.
        # Writing the model trait also persists the new angle to preferences
        # via the observer on DeviceViewMainModel.
        self.model.device_rotation_deg = (int(self.model.device_rotation_deg or 0) + int(angle_step)) % 360
        # undo rotation on text for maintaining readability
        self.electrode_view_layer.rotate_electrode_views_texts(-angle_step)

        self.device_view.fit_to_scene_rect()
        self._set_hud(f"Device orientation: {self._get_device_rotation_deg()} deg")

    def _apply_pan_mode(self):
        enabled = self.model.mode == "pan"

        # Disable interaction with items (clicking/hovering) while panning
        self.device_view.setInteractive(not enabled)

        if enabled:
            self.device_view.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        else:
            self.device_view.setDragMode(QGraphicsView.DragMode.NoDrag)

    def get_electrode_view_for_scene_pos(self, scene_pos):
        return self.device_view.scene().get_item_under_mouse(scene_pos, ElectrodeView)

    def detect_droplet(self):
        """Placeholder for a context menu action."""
        publish_message(topic=DETECT_DROPLETS,
                        message=json.dumps(list(self.model.electrodes.channels_electrode_ids_map.keys())))

    #######################################################################################################
    # Perspective Handlers
    #######################################################################################################

    def handle_reference_point_placement(self, point: QPointF):
        """Handle the placement of a reference point for perspective correction."""
        # Add the new point to the reference rect
        self.rect_buffer.append(point)

    def handle_perspective_edit_start(self, point: QPointF):
        """Handle the start of perspective editing."""
        closest_point, closest_index = self.model.camera_perspective.get_closest_point(point)
        self.rect_editing_index = closest_index  # Store the index of the point being edited

    def handle_perspective_edit(self, point: QPointF):
        """Handle the editing of a reference point during perspective correction."""

        # check if we are editing just the reference rect buffer or the actual rect tied to transforming perspective
        if self._edit_reference_rect:
            logger.debug("Only reference rect buffer changed")
            if not self.rect_buffer:
                self.rect_buffer = self.model.camera_perspective.transformed_reference_rect.copy()
            rect_to_edit = self.rect_buffer
        else:
            logger.debug("Reference rect tied to perspective transform changed")
            rect_to_edit = self.model.camera_perspective.transformed_reference_rect

        rect_to_edit[self.rect_editing_index] = point

    def handle_perspective_edit_end(self):
        """Finalize the perspective editing."""
        self.rect_editing_index = -1

    def handle_rotate_device(self):
        self._rotate_device_view(90)

    def handle_rotate_camera(self):
        self.model.camera_perspective.rotate_output(90)

    def handle_toggle_edit_reference_rect(self):
        if self._edit_reference_rect:
            logger.info(f"Toggling reference rect edit mode off. Changed will affect camera perspective")
        else:
            logger.info(f"Toggling reference rect edit mode on. Changed will not affect camera perspective")

        self._edit_reference_rect = not self._edit_reference_rect

    #######################################################################################################
    # Electrode Handlers
    #######################################################################################################

    def handle_electrode_hover(self, electrode_view: ElectrodeView):
        self.electrode_hovered = electrode_view

    def handle_electrode_channel_editing(self, electrode: Electrode):
        self.model.electrodes.electrode_editing = electrode

    def handle_channel_label_press(self, event) -> bool:
        """In channel-edit mode, a left-click on an electrode enters (or
        switches to) inline label editing.

        Returns True when a NEW edit is started — the caller consumes the press
        so the whole value stays selected (type to replace). Returns False for
        clicks inside the field already being edited, letting Qt place the caret
        or start a drag-selection."""
        if self.model.mode != "channel-edit" or event.button() != Qt.LeftButton:
            return False
        electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
        if electrode_view is None:
            return False
        if getattr(self, "_editing_view", None) is electrode_view:
            return False  # already editing this label — in-field click
        self._begin_channel_label_edit(electrode_view)
        return True

    def _begin_channel_label_edit(self, electrode_view):
        # Commit and close any editor already open before opening the new one —
        # only one label edits at a time. Done explicitly (not via focus-out) so
        # the switch is deterministic regardless of focus event ordering.
        if getattr(self, "_editing_view", None) is not None:
            self._on_channel_label_committed()

        self.model.electrodes.electrode_editing = electrode_view.electrode  # highlight
        self._editing_view = electrode_view

        text_item = electrode_view.text_path
        text_item.editing_committed.connect(self._on_channel_label_committed)
        text_item.editing_cancelled.connect(self._on_channel_label_cancelled)
        electrode_view.enter_label_edit()

    def _end_channel_label_edit(self):
        electrode_view = getattr(self, "_editing_view", None)
        if electrode_view is None:
            return
        text_item = electrode_view.text_path
        try:
            text_item.editing_committed.disconnect(self._on_channel_label_committed)
            text_item.editing_cancelled.disconnect(self._on_channel_label_cancelled)
        except (RuntimeError, TypeError):
            pass  # already disconnected
        electrode_view.exit_label_edit()
        self._editing_view = None
        # Snap the label back to the model value: on commit this repaints the
        # committed number; on cancel/revert it discards the typed text.
        self.electrode_view_layer.redraw_electrode_labels(self.model)

    def _on_channel_label_committed(self):
        electrode_view = getattr(self, "_editing_view", None)
        if electrode_view is None:
            return
        new_channel = self._parse_channel_text(electrode_view.text_path.toPlainText())
        if new_channel is not _CHANNEL_REVERT:
            # Writing the channel fires the label-redraw observer; we still tear
            # down below to reset interaction state.
            electrode_view.electrode.channel = new_channel
        self._end_channel_label_edit()

    def _on_channel_label_cancelled(self):
        self._end_channel_label_edit()

    def _parse_channel_text(self, text):
        """Map raw field text to a channel value: '' -> None (unassign), an
        in-range int -> that int, anything else -> _CHANNEL_REVERT (keep the
        prior value)."""
        text = text.strip()
        if text == "":
            return None
        try:
            value = int(text)
        except ValueError:
            return _CHANNEL_REVERT  # digits are blocked live, so unexpected
        n_channels = self.device_viewer_preferences.NUMBER_OF_CHANNELS
        if 0 <= value < n_channels:
            return value
        return _CHANNEL_REVERT

    def handle_electrode_click(self, electrode_id: Str):
        """Handle an electrode click event."""
        if self.model.mode == "channel-edit":
            self.model.electrode_editing = self.model.electrodes[electrode_id]

        elif self.model.mode in ("edit", "draw", "edit-draw", "merge"):
            clicked_electrode_channel = self.model.electrodes[electrode_id].channel
            if clicked_electrode_channel != None: # The channel can be unassigned!
                if clicked_electrode_channel in self.model.electrodes.disabled_channels:
                    return  # Disabled electrodes cannot be actuated

                if clicked_electrode_channel in self.model.electrodes.actuated_channels:
                    self.model.electrodes.actuated_channels.remove(clicked_electrode_channel)
                else:
                    self.model.electrodes.actuated_channels.add(clicked_electrode_channel)

    def handle_toggle_electrode_tooltips(self, checked):
        """Handle toggle electrode tooltip."""
        self._electrode_tooltip_visible = checked
        self.electrode_view_layer.toggle_electrode_tooltips(checked)

    #######################################################################################################
    # Route Handlers
    #######################################################################################################

    def handle_route_draw(self, from_id, to_id):
        '''Handle a route segment being drawn or first electrode being added'''
        if self.model.mode in ("edit", "edit-draw", "draw"):
            if self.model.mode == "draw": # Create a new layer
                self.model.routes.add_layer(Route(route=[from_id, to_id]))
                self.model.routes.selected_layer = self.model.routes.layers[-1] # Select the route we just added
                self.model.mode = "edit-draw" # We now want to extend the route we just made
            else: # In some edit mode, try to modify currently selected layer
                current_route = self.model.routes.get_selected_route()
                if current_route == None: return

                if current_route.can_add_segment(from_id, to_id):
                    current_route.add_segment(from_id, to_id)

    def handle_route_erase(self, from_id, to_id):
        '''Handle a route segment being erased'''
        current_route = self.model.routes.get_selected_route()
        if current_route == None: return

        if current_route.can_remove(from_id, to_id):
            new_routes = [Route(route_list) for route_list in current_route.remove_segment(from_id, to_id)]
            self.model.routes.replace_layer(self.model.routes.selected_layer, new_routes)

    def handle_endpoint_erase(self, electrode_id):
        '''Handle the erase being triggered by hovering an endpoint'''
        current_route = self.model.get_selected_route()
        if current_route == None: return

        endpoints = current_route.get_endpoints()
        segments = current_route.get_segments()
        if len(endpoints) == 0 or len(segments) == 0: # Path of length 0 or path length of 1
            self.model.routes.delete_layer(self.model.routes.selected_layer) # Delete layer
        elif electrode_id == endpoints[0]: # Starting endpoint erased
            self.handle_route_erase(*segments[0]) # Delete the first segment
        elif electrode_id == endpoints[1]: # Ending endpoint erased
            self.handle_route_erase(*segments[-1]) # Delete last segment

    def handle_autoroute_start(self, from_id, avoid_collisions=True): # Run when the user enables autorouting an clicks on an electrode
        logger.debug("Start Autoroute")
        routes = [layer.route for layer in self.model.routes.layers]
        self.autoroute_paths = find_shortest_paths(from_id, self.model.electrodes.svg_model.neighbours, routes, avoid_collisions=avoid_collisions) # Run the BFS and cache the result dict
        self.model.routes.autoroute_layer = RouteLayer(route=Route(), color=AUTOROUTE_COLOR)

    def handle_autoroute(self, to_id):
        logger.debug(f"Autoroute: Adding route to {to_id}")
        self.model.routes.autoroute_layer.route.route = self.autoroute_paths.get(to_id, []).copy() # Display cached result from BFS

    def handle_autoroute_end(self):
        # only proceed if there is at least one segment and autoroute layer exists
        if self.model.routes.autoroute_layer:
            logger.debug("End Autoroute")
            self.autoroute_paths = {}
            if self.model.routes.autoroute_layer.route.get_segments():
                self.model.routes.add_layer(self.model.routes.autoroute_layer.route) # Keep the route, generate a normal color
            self.model.routes.autoroute_layer = None
            self.model.routes.selected_layer = self.model.routes.layers[-1] # Select just created layer
            # self.model.mode = 'edit'
        else:
            logger.warning("Autoroute needs to start by clicking and dragging from an electrode polygon.")

    #######################################################################################################
    # Key handlers
    #######################################################################################################

    def handle_ctrl_key_left(self):
        self.model.camera_perspective.rotate_output(-90)

    def handle_ctrl_key_right(self):
        self.model.camera_perspective.rotate_output(90)

    def handle_alt_key_left(self):
        angle_step = -90
        self._rotate_device_view(angle_step)

    def handle_alt_key_right(self):
        angle_step = 90
        self._rotate_device_view(angle_step)

    def handle_ctrl_mouse_wheel_event(self, angle):

        if angle > 0:
            self.model.zoom_in_event = True
        else:
            self.model.zoom_out_event = True

    def handle_ctrl_plus(self):
        self.model.zoom_in_event = True # Observer routine will call zoom in

    def handle_ctrl_minus(self):
        self.model.zoom_out_event = True # Observer routine will call zoom out

    def handle_space(self):
        self.model.flip_mode_activation(mode='pan')
        # Observer routine will call apply pan mode #

    ##########################################################################################
    # Electrode Scene global input delegations
    ##########################################################################################

    def handle_key_press_event(self, event: QKeyEvent):
        key = event.key()

        # Arrow-key stepping (keyboard).
        # Only when Ctrl/Alt are NOT held to avoid conflicts with existing shortcuts.
        if not (event.modifiers() & (Qt.ControlModifier | Qt.AltModifier)):
            # We accept either Qt6 enum style (Qt.Key.Key_Left) or legacy aliases.
            key_left = {getattr(Qt, "Key_Left", None), getattr(getattr(Qt, "Key", None), "Key_Left", None)}
            key_right = {getattr(Qt, "Key_Right", None), getattr(getattr(Qt, "Key", None), "Key_Right", None)}
            key_up = {getattr(Qt, "Key_Up", None), getattr(getattr(Qt, "Key", None), "Key_Up", None)}
            key_down = {getattr(Qt, "Key_Down", None), getattr(getattr(Qt, "Key", None), "Key_Down", None)}
            if key in key_left:
                self._step_active_electrodes(self._map_direction_for_device_rotation("left"))
            elif key in key_right:
                self._step_active_electrodes(self._map_direction_for_device_rotation("right"))
            elif key in key_up:
                self._step_active_electrodes(self._map_direction_for_device_rotation("up"))
            elif key in key_down:
                self._step_active_electrodes(self._map_direction_for_device_rotation("down"))

        if (event.modifiers() & Qt.ControlModifier):
            if event.key() == Qt.Key_Right:
                self.handle_ctrl_key_right()

            if event.key() == Qt.Key_Left:
                self.handle_ctrl_key_left()

            # Check for Plus (Key_Plus is Numpad, Key_Equal is standard keyboard '+')
            if event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.handle_ctrl_plus()

            if event.key() == Qt.Key.Key_Minus:
                self.handle_ctrl_minus()

        if (event.modifiers() & Qt.AltModifier):
            if event.key() == Qt.Key_Right:
                self.handle_alt_key_right()

            elif event.key() == Qt.Key_Left:
                self.handle_alt_key_left()

        if event.key() == Qt.Key.Key_Space:
            self.handle_space()

    def handle_mouse_press_event(self, event):
        """Handle the start of a mouse click event."""

        button = event.button()
        mode = self.model.mode

        electrode_view =  self.get_electrode_view_for_scene_pos(event.scenePos())
        if button == Qt.LeftButton:
            self._left_mouse_pressed = True

            if mode in ("edit", "draw", "edit-draw"):
                if electrode_view:
                    self._last_electrode_id_visited = electrode_view.id

            elif mode == "auto":
                if electrode_view:
                    is_alt_pressed = event.modifiers() & Qt.KeyboardModifier.AltModifier
                    self.handle_autoroute_start(electrode_view.id,
                                                                    avoid_collisions=not is_alt_pressed)

            elif mode == "channel-edit":
                if electrode_view:
                    self.handle_electrode_channel_editing(electrode_view.electrode)

            elif mode == "camera-place":
                self.handle_reference_point_placement(event.scenePos())

            elif mode == "camera-edit":
                self.handle_perspective_edit_start(event.scenePos())

        elif button == Qt.RightButton:
            self._right_mouse_pressed = True
            if electrode_view:
                self.model.electrodes.electrode_right_clicked = electrode_view.electrode
            else:
                self.model.electrodes.electrode_left_clicked = None



    def handle_mouse_move_event(self, event):
        """Handle the dragging motion."""

        mode = self.model.mode
        electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
        self.handle_electrode_hover(electrode_view)

        if self._left_mouse_pressed:
            # Only proceed if we are in the appropriate mode with a valid electrode view.
            # If last electrode view is none then no electrode was clicked yet (for example, first click was not on electrode)
            if mode in ("edit", "draw", "edit-draw") and electrode_view and self._last_electrode_id_visited:

                found_connection_item = find_path_item(self.device_view.scene(),
                                                           (self._last_electrode_id_visited, electrode_view.id))

                if found_connection_item:  # Are the electrodes neighbours? (This excludes self)
                    self.handle_route_draw(self._last_electrode_id_visited, electrode_view.id)
                    self._is_drag = True  # Since more than one electrode is left clicked, its a drag, not a single electrode click

            elif mode == "auto" and electrode_view:
                # only proceed if a new electrode id was visited
                if electrode_view.id != self._last_electrode_id_visited:
                    self.handle_autoroute(electrode_view.id)  # We store last_electrode_id_visited as the source node

            elif mode == "camera-edit":
                self.handle_perspective_edit(event.scenePos())

        if self._right_mouse_pressed:
            if mode in ("edit", "draw", "edit-draw") and event.modifiers() & Qt.ControlModifier:
                connection_item = self.device_view.scene().get_item_under_mouse(event.scenePos(), ElectrodeConnectionItem)
                endpoint_item = self.device_view.scene().get_item_under_mouse(event.scenePos(), ElectrodeEndpointItem)
                if connection_item:
                    (from_id, to_id) = connection_item.key
                    self.handle_route_erase(from_id, to_id)
                elif endpoint_item:
                    self.handle_endpoint_erase(endpoint_item.electrode_id)

        # End of routine: now the current electrode view becomes the "last electrode visited"
        if electrode_view:
            self._last_electrode_id_visited = electrode_view.id

    def handle_mouse_release_event(self, event):
        """Finalize the drag operation."""
        button = event.button()

        if button == Qt.LeftButton:
            self._left_mouse_pressed = False
            mode = self.model.mode
            if mode == "auto":
                self.handle_autoroute_end()

            elif mode in ("edit", "draw", "edit-draw"):
                electrode_view = self.get_electrode_view_for_scene_pos(event.scenePos())
                # If it's a click (not a drag) since only one electrode selected:
                if not self._is_drag and electrode_view:
                    self.handle_electrode_click(electrode_view.id)

                # Reset left-click related vars
                self._is_drag = False

                if mode == "edit-draw":  # Go back to draw
                    self.model.mode = "draw"
            elif mode == "camera-edit":
                self.handle_perspective_edit_end()
        elif button == Qt.RightButton:
            self._right_mouse_pressed = False

    def handle_scene_wheel_event(self, event: 'QGraphicsSceneWheelEvent'):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.delta()
            self.handle_ctrl_mouse_wheel_event(angle)
            event.accept()
            return True
        else:
            return False

    def handle_wheel_event(self, event: 'QWheelEvent'):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            self.handle_ctrl_mouse_wheel_event(angle)
            event.accept()
            return True
        else:
            return False

    def handle_context_menu_event(self, event: QGraphicsSceneContextMenuEvent):

        if not (event.modifiers() & Qt.ControlModifier): # If control is pressed, we do not show the context menu

            context_menu = QMenu()

            if self.model.mode.split("-")[0] == "camera":
                def set_camera_place_mode():
                    self.model.mode = "camera-place"

                reference_rect_edit_action = QAction("Edit Reference Rect", checkable=True,
                                              checked=self._edit_reference_rect,
                                              toolTip="Edit Reference Rectangle without changing camera perspective")

                reference_rect_edit_action.triggered.connect(self.handle_toggle_edit_reference_rect)

                context_menu.addAction("Reset Reference Rectangle", set_camera_place_mode)
                context_menu.addAction(reference_rect_edit_action)
                context_menu.addSeparator()

            else:
                context_menu.addAction("Measure Liquid Capacitance", self.model.measure_liquid_capacitance)
                context_menu.addAction("Measure Filler Capacitance", self.model.measure_filler_capacitance)
                context_menu.addSeparator()
                context_menu.addAction("Clear Electrodes", self.model.electrodes.clear_electrode_states)
                context_menu.addAction("Clear Routes", self.model.routes.clear_routes)
                context_menu.addSeparator()
                context_menu.addAction("Find Liquid", self.detect_droplet)
                context_menu.addSeparator()

                # Bulk enable/disable all electrodes
                has_disabled = len(self.model.electrodes.disabled_channels) > 0

                def enable_all_electrodes():
                    self.model.electrodes.disabled_channels.clear()

                def disable_all_electrodes():
                    all_channels = set(self.model.electrodes.channels_electrode_ids_map.keys())
                    self.model.electrodes.disabled_channels = all_channels

                if has_disabled:
                    context_menu.addAction("Enable All Electrodes", enable_all_electrodes)
                context_menu.addAction("Disable All Electrodes", disable_all_electrodes)
                context_menu.addSeparator()

                if self.model.electrodes.electrode_right_clicked is not None:
                    right_clicked = self.model.electrodes.electrode_right_clicked
                    channel = right_clicked.channel

                    # Disable/Enable electrode toggle
                    if channel is not None:
                        is_disabled = channel in self.model.electrodes.disabled_channels
                        label = "Enable Electrode" if is_disabled else "Disable Electrode"

                        def toggle_disable(ch=channel, currently_disabled=is_disabled):
                            if currently_disabled:
                                self.model.electrodes.disabled_channels.discard(ch)
                            else:
                                self.model.electrodes.disabled_channels.add(ch)

                        context_menu.addAction(label, toggle_disable)

                    scale_edit_view_controller = ScaleEditViewController(model=self.model)

                    context_menu.addAction("Adjust Electrode Area Scale", scale_edit_view_controller.configure_traits)
                    context_menu.addSeparator()

            # tooltip enabled by default
            tooltip_toggle_action = QAction("Enable Electrode Tooltip", checkable=True,
                                            checked=self._electrode_tooltip_visible)

            tooltip_toggle_action.triggered.connect(self.handle_toggle_electrode_tooltips)

            context_menu.addAction(tooltip_toggle_action)

            context_menu.exec(event.screenPos())

    ################################################################################################################
    # ------------------ Traits observers --------------------------------------------
    ################################################################################################################

    @observe("model.routes.layers.items.visible")
    @observe("model.routes.selected_layer")
    @observe("model.routes.layers.items.route.route.items")
    @observe("model.routes.layers.items")
    @observe("model.routes.autoroute_layer.route.route.items")
    def route_redraw(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_connections_to_scene(self.model)

    @observe("model.electrodes.electrode_editing")
    @observe("model.electrodes.electrodes.items.channel")
    def electrode_state_recolor(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_colors(
                self.model,
                self.electrode_hovered,
            )

    @observe("model.electrodes.electrode_editing")
    def _teardown_label_edit_on_deselect(self, event):
        # Leaving channel-edit mode clears electrode_editing (main_model), so an
        # open editor is cancelled and reset along with the deselection.
        if event.new is None and getattr(self, "_editing_view", None) is not None:
            self._end_channel_label_edit()

    @observe("model.electrodes.actuated_channels.items")
    @observe("model.electrodes.disabled_channels.items")
    def actuation_state_recolor(self, event):
        """Recolor only the electrodes whose channels changed — the hot
        path during protocol runs (each phase touches a handful of the
        board's channels).

        Two event shapes arrive here: in-place mutation gives a
        SetChangeEvent (added/removed); wholesale replacement — what
        RouteExecutionService._apply_phase does every phase — gives the
        container change event (old/new sets), diffed here by symmetric
        difference (= exactly the channels whose membership flipped)."""
        if not self.electrode_view_layer:
            return
        added = getattr(event, "added", None)
        removed = getattr(event, "removed", None)
        if added is not None or removed is not None:
            changed_channels = set(added or ()) | set(removed or ())
        else:
            old, new = getattr(event, "old", None), getattr(event, "new", None)
            if not isinstance(old, (set, frozenset)) or not isinstance(new, (set, frozenset)):
                # Unknown event shape: recolor everything rather than guess.
                self.electrode_view_layer.redraw_electrode_colors(
                    self.model, self.electrode_hovered)
                return
            changed_channels = old ^ new
        self.electrode_view_layer.redraw_electrode_colors_for_channels(
            self.model, changed_channels, self.electrode_hovered)

    @observe("electrode_hovered")
    def hovered_electrode_recolor(self, event):
        """Hover only affects the two electrodes involved; recoloring the
        whole board per mouse move made hovering expensive."""
        if not self.electrode_view_layer:
            return
        for electrode_view in (event.old, event.new):
            if electrode_view is not None:
                self.electrode_view_layer.recolor_electrode(
                    self.model, electrode_view, self.electrode_hovered)

    @observe("model.electrodes.electrodes.items.channel")
    def electrode_channel_change(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_labels(self.model)

    @observe("model:camera_perspective:transformed_reference_rect")
    def _reference_rect_change(self, event):
        logger.debug(f"Reference rectangle change: {event}")
        if self.electrode_view_layer and self.model.mode.split("-")[0] == "camera":
            self.electrode_view_layer.redraw_reference_rect(rect=event.new)

    @observe("model:camera_perspective:transformed_reference_rect:items")
    def _reference_rect_items_change(self, event):
        logger.debug(f"Reference rectangle items change: {event}")
        if self.electrode_view_layer and self.model.mode.split("-")[0] == "camera":
            self.electrode_view_layer.redraw_reference_rect(rect=event.object)

    @observe("rect_buffer:items")
    def _rect_buffer_change(self, event):
        logger.debug(f"rect_buffer change: adding point {event.added}. Buffer of length {len(self.rect_buffer)} now.")
        if len(self.rect_buffer) == 4:  # We have a rectangle now

            inverse = self.model.camera_perspective.transformation.inverted()[0]  # Get the inverse of the existing transformation matrix
            self.model.camera_perspective.reference_rect = [inverse.map(point) for point in event.object]
            self.model.camera_perspective.transformed_reference_rect = self.rect_buffer.copy()

            # User may have already completed the reference rectangle and in edit mode.
            # sometimes user is just editing a completed rect_buffer when edit_reference_rect is enabled
            # Only need to do this and give log message when its the first time the reference rect is completed.
            if self.model.mode != "camera-edit":
                logger.info(f"Reference rectangle complete!\nProceed to camera perspective editing!!")
                self.model.mode = "camera-edit"  # Switch to camera-edit mode if not already there

        else:
            self.electrode_view_layer.redraw_reference_rect(rect=event.object)

    @observe("model:mode")
    def _on_mode_change(self, event):
        if event.old in ("camera-edit", "camera-place") and event.new != "camera-edit":
            self.electrode_view_layer.clear_reference_rect()

        if event.new == "camera-edit":
            self.electrode_view_layer.redraw_reference_rect(self.model.camera_perspective.transformed_reference_rect)

        if event.old != "camera-place" and event.new == "camera-place":
            self.rect_buffer.clear()

        if event.new == 'pan' or event.old == 'pan':
            self._apply_pan_mode()

    @observe('model.electrode_scale', post_init=True)
    def electrode_area_scale_edited(self, event):
        if self.electrode_view_layer:
            self.electrode_view_layer.redraw_all_electrode_tooltips()

    @observe("model.alpha_map.items.[alpha, visible]", post_init=True)
    def _alpha_change(self, event):

        changed_key = event.object.key

        if changed_key == electrode_outline_key and self.electrode_view_layer:
            self.electrode_view_layer.redraw_electrode_lines(self.model)

        if changed_key in [electrode_fill_key, actuated_electrodes_key]:
            self.electrode_state_recolor(None)

        if changed_key == electrode_text_key:
            self.electrode_channel_change(None)

        if changed_key in (routes_key, connections_key):
            self.route_redraw(None)

    @observe("model:zoom_in_event", post_init=True)
    def _zoom_in_event_triggered(self, event):
        self._zoom_in()

    @observe("model:zoom_out_event", post_init=True)
    def _zoom_out_event_triggered(self, event):
        self._zoom_out()

    @observe("model:reset_view_event", post_init=True)
    def _reset_view_event_triggered(self, event):
        self.device_view.fit_to_scene_rect()
