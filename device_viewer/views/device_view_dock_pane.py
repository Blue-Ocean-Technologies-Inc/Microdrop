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
from functools import partial
from pathlib import Path

# Enthought library imports.
from pyface.qt.QtCore import QPointF, QRectF, QSizeF, Qt, QTimer
from pyface.qt.QtGui import QBrush, QColor, QFont, QGraphicsScene, QImage, QPainter
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem
from pyface.qt.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QMenu,
    QPushButton,
    QScrollArea,
    QWidget,
)
from pyface.tasks.api import TraitsDockPane
from pyface.undo.api import CommandStack, UndoManager
from traits.api import Bool, Instance, List, observe
from traitsui.api import UI
from traitsui.view import View

# Microdrop package imports.
from microdrop_application.dialogs.pyface_wrapper import (
    CANCEL,
    NO,
    OK,
    YES,
    FileDialog,
    confirm,
    error,
    information,
    warning,
)
from microdrop_status_bar.consts import ICON_PRIORITY_LEFT
from notifications.consts import LOG_RECORDED_EXTRA

# Microdrop style imports.
from microdrop_style.button_styles import get_tooltip_style
from microdrop_style.colors import BLACK
from microdrop_style.fonts.fontnames import ICON_FONT_FAMILY
from microdrop_style.helpers import (
    QT_THEME_NAMES,
    get_complete_stylesheet,
    is_dark_mode,
)
from microdrop_style.icon_styles import STATUSBAR_ICON_POINT_SIZE

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.file_handler import safe_copy_file
from microdrop_utils.keyboard_shortcuts_view import show_keyboard_shortcuts
from microdrop_utils.lazy_dock_pane import LazyContentDockPane
from microdrop_utils.pyface_helpers import app_statusbar_message_from_dock_pane
from microdrop_utils.pyside_helpers import (
    PulsingLabel,
)

# Local imports.
from ..consts import (
    ALIGNMENT_DEVICE_RENDER_WIDTH_PX,
    AUTO_COMMIT_DEBOUNCE_MS,
    DEVICE_VIEWER_LAYERS,
    KEYBOARD_SHORTCUT_GROUPS,
    KEYBOARD_SHORTCUTS,
    KEYBOARD_SHORTCUTS_TITLE,
    MASTER_SVG_FILE,
    PKG,
    STEP_PARAMS_COMMIT,
    ZONE_STATUS_MESSAGE_MS,
    PKG_name,
    camera_edit_status_message_text,
    camera_place_status_message_text,
    device_modified_tag,
)
from ..controllers.calibration_reminder_controller import (
    CalibrationReminderController,
)
from ..controllers.camera_alignment_controller import (
    CameraAlignmentWorkflowController,
)
from ..controllers.device_load_controller import DeviceLoadController
from ..controllers.device_viewer_message_controller import (
    DeviceViewerMessageController,
)
from ..controllers.device_viewer_publish_controller import (
    DeviceViewerPublishController,
)
from ..controllers.layer_host import LayerHost
from ..controllers.sidebar_section_builder import SidebarSectionBuilder
from ..controllers.zones_controller import ZonesController
from ..default_settings import ELECTRODE_OFF, video_key
from ..interfaces.layer_context import LayerContext
from ..models.alpha import AlphaValue
from ..models.connections_editor import ConnectionsEditorModel
from ..models.deferred_sidebar_section import DeferredSidebarSection
from ..models.electrodes import Electrodes
from ..models.main_model import DeviceViewMainModel
from ..models.messages import DeviceViewerMessageModel
from ..models.route import Route
from ..models.step_params_commit import StepParamsCommitMessage
from ..preferences import (
    DeviceViewerAdvancedPreferences,
    DeviceViewerPreferences,
    sidebar_settings_grid,
)
from ..services.electrode_interaction_service import (
    ElectrodeInteractionControllerService,
)
from ..services.electrode_stepping_service import ElectrodeSteppingService
from ..services.keyboard_shortcut_service import KeyboardShortcutService
from ..services.svg_persistence_service import (
    SvgPersistenceService,
    is_bundled_device,
)
from ..utils.alignment_geometry import device_render_rect
from ..utils.auto_fit_graphics_view import AutoFitGraphicsView
from .connections_editor_view.connections_editor_pane import ConnectionsEditorPane
from .electrode_view.electrode_layer import ElectrodeLayer
from .electrode_view.electrode_scene import ElectrodeScene
from .sidebar.calibration import build_calibration
from .sidebar.camera_controls import build_camera_controls
from .sidebar.host import build_reveal_button, build_sidebar
from .sidebar.paths import build_paths
from .sidebar.section import SidebarSection, SizedSidebarSection
from .sidebar.viewport_controls import build_viewport_controls
from .sidebar.zones import build_zones

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

_dock_pane_name = f"{PKG_name} Dock Pane"


# Debounce delay (ms) so arrow-key navigation publishes once after movement stops
# ELECTRODE_PUBLISH_DEBOUNCE_MS = 0


class DeviceViewerDockPane(LazyContentDockPane, TraitsDockPane):
    """
    A widget for viewing the device. This puts the electrode layer into a graphics view.

    The device is loaded into the model, and announced, when the pane is
    created; the view is built the first time the pane is shown, or when a
    camera request or a menu action needs it (#1087).
    """

    # ----------- Device View Pane traits ---------------------

    undo_manager = Instance(UndoManager)

    model = Instance(DeviceViewMainModel)

    id = PKG + ".dock_pane"
    name = _dock_pane_name

    # Views
    scene = Instance(QGraphicsScene)
    device_view = Instance(AutoFitGraphicsView)
    device_viewer_preferences = Instance(DeviceViewerPreferences)
    current_electrode_layer = Instance(ElectrodeLayer, allow_none=True)

    #: Camera controls widget; None until the Camera Controls section is
    #: built, which follows the pane's build (see
    #: ``when_camera_controls_built``).
    camera_control_widget = None

    #: The open Edit Connections dialog; None while closed.
    _connections_editor_ui = Instance(UI)

    #: The sidebar's sections, top to bottom; holding them keeps each
    #: section's controllers and TraitsUI UIs alive with the pane.
    sidebar_sections = List(Instance(SidebarSection))

    #: Builds the deferred sidebar sections after the pane's build (#1064).
    sidebar_builder = Instance(SidebarSectionBuilder)

    #: The deferred Camera Controls section; pub/sub camera requests wait
    #: on it.
    _camera_controls_section = Instance(DeferredSidebarSection)

    #: Keeps zone edits in step with the main model, with or without the
    #: Zones section built.
    zones_controller = Instance(ZonesController)

    #: The open sidebar layout preferences editor; None until opened.
    edit_sidebar_layout_ui = Instance(UI)

    #: The sidebar's scroll area, the widget it scrolls, and the button
    #: that reveals it; None until ``create_contents`` builds them.
    scroll_area = Instance(QScrollArea)
    scroll_content = Instance(QWidget)
    reveal_button = Instance(QPushButton)

    #: Loads devices into the model, whether or not the view is built.
    device_loader = Instance(DeviceLoadController)

    #: True once ``create_contents`` has built the view; a device load
    #: rebuilds the view only then.
    device_view_built = Bool(False)

    # Variables
    _last_applied_step_id = Instance(
        str, desc="None means no step applied yet", allow_none=True
    )
    video_item = Instance(
        QGraphicsVideoItem, allow_none=True, desc="The video item for the camera feed"
    )
    # _electrode_publish_timer = None  # Debounce timer for electrode state
    # publish (e.g. arrow-key navigation)

    #: Dramatiq listener for this pane's topics; dispatches them to the pane.
    message_controller = Instance(DeviceViewerMessageController)

    #: Owns the outbound publishing: model observers, the undo/redo entry
    #: points they guard against, and the echo-prevention flags this pane
    #: flips while applying an inbound message (#768).
    publish_controller = Instance(DeviceViewerPublishController)

    #: Owns the camera-alignment endpoint workflow: the per-device
    #: endpoint store, the Camera Alignment dialog, and Go To Endpoint (#781).
    camera_alignment_controller = Instance(CameraAlignmentWorkflowController)

    #: Mounts the layers sibling plugins contribute (#650); None until
    #: ``create_contents`` builds the sidebar they join.
    layer_host = Instance(LayerHost)

    #: Reads and writes the device SVG; the pane title follows its
    #: ``loaded_path`` and ``modified``.
    svg_persistence = Instance(SvgPersistenceService)

    #: Posts the calibration reminder to the notifications drawer.
    calibration_reminder = Instance(CalibrationReminderController)

    #: Restarted by each sidebar edit while auto-commit is due; commits the
    #: edits once they settle.
    _auto_commit_timer = Instance(QTimer)

    # --------- Device View trait initializers -------------
    def traits_init(self):
        ###############################################################################################################
        # --------------Setup device view model ---------------------------------- #
        ##############################################################################################################

        ########### Load preferences: for app level, and device viewer level: #########
        self.app_preferences = (
            self.task.window.application.preferences_helper.preferences
        )
        self.device_viewer_preferences = DeviceViewerPreferences(
            preferences=self.app_preferences
        )

        self.device_viewer_advanced_preferences = DeviceViewerAdvancedPreferences(
            preferences=self.app_preferences
        )

        ################ Load undo manager #####################################

        self.undo_manager = UndoManager(active_stack=CommandStack())
        self.undo_manager.active_stack.undo_manager = self.undo_manager

        ################ Auto-commit debounce ##################################
        # Before the model: its auto_commit_due observer drives this timer.
        self._auto_commit_timer = QTimer()
        self._auto_commit_timer.setSingleShot(True)
        self._auto_commit_timer.setInterval(AUTO_COMMIT_DEBOUNCE_MS)
        self._auto_commit_timer.timeout.connect(self._auto_commit_sidebar_params)

        ################ Create Model ##########################################
        self.model = DeviceViewMainModel(
            undo_manager=self.undo_manager, preferences=self.device_viewer_preferences
        )

        ################################################################################################################
        # ------------------Load preferences to model ---------------------------#
        ################################################################################################################

        ############## Load preferred / default svg ####################################

        self.svg_persistence = SvgPersistenceService(
            model=self.model, preferences=self.device_viewer_preferences
        )

        ############## load preferred / default camera options #########################
        self.model.load_camera_perspective_from_preferences()

        ############## load preferred / default device-view rotation ###################
        self.model.load_device_perspective_from_preferences()

        ############## load last-session calibration data ##############################
        self.model.load_calibration_data_from_preferences()

        # Its reminder (Needs attention), once the data has loaded: this
        # runs as the pane is first shown, after the window has painted.
        self.calibration_reminder = CalibrationReminderController(
            calibration=self.model.calibration
        )
        self.calibration_reminder.start()

        ################################################################################################
        # ----------- Setup device view widget ----------------- #
        ################################################################################################

        self.scene = ElectrodeScene()
        self.device_view = AutoFitGraphicsView(
            self.scene,
            auto_fit_margin_scale=self.device_viewer_preferences._auto_fit_margin_scale,
        )
        self.device_view.setObjectName("device_view")

        # Display states reach the model from launch, built view or not; a
        # view built later shows the model as it is then.
        self.device_view.display_state_signal.connect(self.apply_message_model)

        # Owns the outbound publishing; created before the message
        # controller so its inbound handlers can already reach it.
        self.publish_controller = DeviceViewerPublishController(model=self.model)

        self.device_loader = DeviceLoadController(
            svg_persistence=self.svg_persistence,
            publish_controller=self.publish_controller,
            preferences=self.device_viewer_preferences,
        )

        # Per-device saved endpoints and the combined endpoint/outline
        # alignment dialog.
        self.camera_alignment_controller = CameraAlignmentWorkflowController(
            model=self.model,
            get_video_item=lambda: self.video_item,
            get_electrode_layer=lambda: self.current_electrode_layer,
            render_device_image=self._render_device_image,
            get_dialog_parent=lambda: self.device_view.window(),
            statusbar_message=self._statusbar_message,
            get_camera_label=lambda: (
                self.camera_control_widget.camera_model.selected_camera
                if self.camera_control_widget is not None
                else ""
            ),
        )

        self._create_sidebar_builder()

        # Last: its handlers dereference the model, view, and preferences.
        self.message_controller = DeviceViewerMessageController(pane=self)

    ################################################################################################
    # ------- Phase-navigation mode -------------
    ################################################################################################

    def apply_phase_navigation_mode(self, enabled):
        """Apply an inbound phase-navigation mode without re-broadcasting it."""
        if self.model is None:
            return

        self.publish_controller._applying_phase_nav_message = True

        try:
            self.model.phase_navigation_mode = enabled
        finally:
            self.publish_controller._applying_phase_nav_message = False

    ################################################################################################
    # ------- Offscreen device render (camera alignment, connections editor) -------
    ################################################################################################

    def _render_device_image(self, width_px=ALIGNMENT_DEVICE_RENDER_WIDTH_PX):
        """Just the device SVG, rendered offscreen at FULL visibility —
        a throwaway ElectrodeLayer with its own alphas and fills, so
        neither the live view's camera feed/routes nor its current
        alpha/visibility settings (camera modes hide fill and text)
        can blank out parts of the device. Fresh ElectrodeViews carry
        no color stack until a recolor pass runs, so the fills are
        painted explicitly here. Returns (QImage, the device-scene
        rect the image covers), or (None, None) when the device has
        no drawable geometry."""
        full_alphas = {
            key: 1.0 for key in self.device_viewer_preferences.default_alphas
        }
        layer = ElectrodeLayer(self.model.electrodes, full_alphas)
        scene = QGraphicsScene()
        layer.add_electrodes_to_scene(scene)
        for electrode_view in layer.electrode_views.values():
            electrode_view.update_color([QColor(ELECTRODE_OFF)])

        rect = layer.get_electrodes_views_bounding_rect()
        if rect.isEmpty():
            return None, None

        # A small margin so edge outlines don't clip at the image
        # border; the padded rect is also the returned scene bridge,
        # so the pixel <-> scene mapping stays exact.
        rect = QRectF(
            *device_render_rect([rect.x(), rect.y(), rect.width(), rect.height()])
        )
        height_px = max(int(width_px * rect.height() / rect.width()), 1)

        image = QImage(width_px, height_px, QImage.Format_ARGB32_Premultiplied)
        image.fill(QColor(BLACK))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        scene.render(painter, QRectF(0, 0, width_px, height_px), rect)
        painter.end()

        return image, rect

    def _on_camera_frame_size_changed(self, size):
        """The feed's native frame size changed (a camera or resolution
        switch): the alignment presets' picture-shape checks follow it."""
        self.camera_alignment_controller.live_frame_size = (
            None if size.isEmpty() else [float(size.width()), float(size.height())]
        )

    def _close_connections_editor(self):
        if self._connections_editor_ui is not None:
            if self._connections_editor_ui.control is not None:
                self._connections_editor_ui.dispose()

            self._connections_editor_ui = None

    def _statusbar_message(self, message):
        status_bar_manager = self.task.window.status_bar_manager
        if status_bar_manager is not None:
            status_bar_manager.message = message

    @observe("model:zones:move_rejected")
    def _on_zone_move_rejected(self, event):
        """Show the note beside the mode message, not in its place: pyface
        strings the status-bar messages together, and the note goes away
        on its own."""
        status_bar_manager = self.task.window.status_bar_manager
        if status_bar_manager is None:
            return
        message = "Move rejected: regions must stay on the device and contiguous"
        if message not in status_bar_manager.messages:
            status_bar_manager.messages.append(message)

        def remove_note():
            if message in status_bar_manager.messages:
                status_bar_manager.messages.remove(message)

        QTimer.singleShot(ZONE_STATUS_MESSAGE_MS, remove_note)

    ################################################################################################
    # ------- Device View class methods -------------------------
    ################################################################################################
    def undo(self):
        # Delegates to the publish controller, which owns _undoing — the
        # guard that keeps this from being re-recorded onto its own stack.
        self.publish_controller.undo()

    def redo(self):
        self.publish_controller.redo()

    def apply_message_model(self, message_model_serial: str):
        logger.debug(f"Display state triggered with model: {message_model_serial}")

        message_model = DeviceViewerMessageModel.deserialize(message_model_serial)

        step_changed = message_model.step_id != self._last_applied_step_id

        if (
            not step_changed
            and message_model.execution_params
            and not self.model.protocol_running
        ):
            # Same-step refresh: the protocol widget echoing back its own
            # reconciliation (e.g. the tree recalculating Route Reps Dur
            # after the DV wrote routes to the step). Reload + rebaseline
            # the sidebar params, then STOP — falling through to the
            # reset()/reapply below would clear_routes() in the middle of a
            # free-hand draw, wiping the in-progress route and selected
            # layer and kicking the user out of draw mode. Routes only ever
            # flow DV -> tree, never back, so there is nothing else to sync.
            # Electrodes do: the tree can change a selected step's electrodes
            # (e.g. Fill Pattern) without changing the step id.
            channels_activated = set(message_model.channels_activated)

            if self.model.electrodes.actuated_channels != channels_activated:
                self.publish_controller._disable_state_messages = True
                self.publish_controller._undoing = True

                try:
                    self.model.electrodes.electrode_editing = None
                    self.model.electrodes.actuated_channels = channels_activated
                finally:
                    self.publish_controller._disable_state_messages = False
                    self.publish_controller._undoing = False

            if self.model.routes.commit_enabled:
                # The echo carries the step's stored params. While the
                # sidebar holds uncommitted edits (say new lanes, then a
                # route drawn before committing) applying it would revert
                # them; they reach the step when the user commits.
                logger.debug(
                    f"Device Viewer: kept uncommitted sidebar params over the "
                    f"protocol echo for step {message_model.step_id}"
                )
                return

            logger.info(
                f"Device Viewer: Applying new execution params from protocol "
                f"side for step {message_model.step_id};\n\n "
                f"Params: {message_model.execution_params}\n\n"
            )
            self.model.routes.apply_execution_params(message_model.execution_params)
            return

        if step_changed and not self.model.protocol_running:
            if self.model.auto_commit_due:
                # The pending edits belong to the step being left: commit
                # them there now, before the new step's values replace them.
                self._auto_commit_timer.stop()
                self._commit_sidebar_params(self._last_applied_step_id)

            elif message_model.execution_params:
                self._check_unsaved_execution_params()

        if message_model.uuid == self.model.uuid:
            return  # Ignore messages that are from the same model

        # Apply the incoming state as a DIFF — no reset-then-rebuild. The
        # old path cleared every route layer and re-added them one by one,
        # repainting the connection map once per layer with the routes
        # visibly blinking off in between (the per-phase flicker).
        self.publish_controller._disable_state_messages = (
            True  # Prevent state messages from being sent while we apply the new state
        )
        # Prevent changes from being added to the undo stack (otherwise model
        # changes are undone during playback)
        self.publish_controller._undoing = True
        # Suspend the play-checkbox/param-edit rebuild observer while the new
        # step's params/routes are being written below — otherwise it fires
        # mid-apply against the OLD step's execution plan / baseline and
        # corrupts the phase-nav state (#493 review F2). The explicit
        # rebuild_phase_navigation() call at the end of this method performs
        # the single rebuild against the fully-applied new step.
        self.model.route_execution_service.suspend_nav_rebuild = True

        try:
            # Apply step ID
            self.model.step_id = message_model.step_id

            # Apply step label
            self.model.step_label = message_model.step_label

            # Apply free mode
            self.model.free_mode = message_model.free_mode

            # Apply editable state
            self.model.editable = message_model.editable

            if not self.model.protocol_running and self.model.mode == "display":
                self.model.mode = "draw"

            # Electrode->channel mapping is NOT carried on state messages (#415):
            # electrodes keep their geometry-derived channels, so there is
            # nothing to apply here.

            # Apply electrode on/off states in ONE assignment: the recolor
            # observer receives a single old/new event and repaints only the
            # channels whose membership flipped.
            self.model.electrodes.electrode_editing = None
            self.model.electrodes.actuated_channels = set(
                message_model.channels_activated
            )

            # Apply routes only when they actually changed (phase toggles change
            # actuation only) — and then as one list swap, so the connection map
            # repaints exactly once with the final layer stack. This also means
            # the layers are never transiently empty, so repeats_frozen can't
            # flip on mid-apply and pin Repetitions/Repeat Dur to 1/0 before the
            # step's execution params are pulled below.
            #
            # Protocol-side colors are deliberately IGNORED: the tree echoes
            # back whatever it stored, which drifts from (and reorders against)
            # the viewer's palette — the visible symptom was routes flipping
            # between shades on alternate phases. Route colors are the device
            # viewer's own: selected paints yellow and loops CW/CCW at render
            # time; everything else gets the standard pool color.
            incoming_routes = [route for route, _color in message_model.routes]
            current_routes = [
                list(layer.route.route) for layer in self.model.routes.layers
            ]
            if incoming_routes != current_routes:
                self.model.routes.replace_all_layers(
                    [Route(route=route.copy()) for route in incoming_routes]
                )
            self.model.routes.selected_layer = None
            self.model.routes.layer_to_merge = None
            self.model.routes.mode = "draw"
            self.model.routes.message = ""

            # Pull the step's execution params into the sidebar AFTER the routes
            # are in place, then baseline the sidebar so the commit button
            # starts disabled.
            if step_changed:
                if message_model.execution_params:
                    self.model.routes.apply_execution_params(
                        message_model.execution_params
                    )
                else:
                    self.model.routes.clear_committed_baseline()
                self._last_applied_step_id = message_model.step_id

        finally:
            # Re-enable state messages after reset
            self.publish_controller._disable_state_messages = False
            self.publish_controller._undoing = False
            self.model.route_execution_service.suspend_nav_rebuild = False
        self.undo_manager.active_stack.clear()  # Clear the undo stack

        # Publish geometry if the electrode-to-channel mapping changed.
        self.publish_controller._publish_geometry_if_changed()

        # Idle phase navigation follows the newly applied step (#493). Runs
        # after _disable_state_messages is cleared so phase 0's actuation
        # publishes (realtime-gated) like any other nav step.
        if self.model.phase_navigation_mode and not self.model.protocol_running:
            self.model.route_execution_service.rebuild_phase_navigation()

    def _check_unsaved_execution_params(self):
        # ask user if they want to save changes if there are any before moving on
        if not self.model.protocol_running:
            if self.model.routes.commit_enabled and self._last_applied_step_id:
                logger.warning(
                    f"Unsaved route execution settings for last step "
                    f"{self._last_applied_step_id}",
                    extra=LOG_RECORDED_EXTRA,
                )

                choice = warning(
                    None,
                    "Save your execution settings to current protocol step?",
                    title="Uncommitted Execution Settings",
                    informative=(
                        "You've changed this step's execution settings in the "
                        "device viewer but haven't committed them to the "
                        "protocol.<br><br>"
                        "<b>Commit</b> writes them to the step. "
                        "<b>Discard</b> reverts to the step's saved values."
                    ),
                    ok_label="Commit",
                    cancel_label="Discard",
                )

                if choice == CANCEL:
                    logger.debug("Discarding unsaved route execution settings")

                elif choice == OK:
                    self._commit_sidebar_params(self._last_applied_step_id)

    def _commit_sidebar_params(self, step_id):
        """Publish the sidebar's settings to ``step_id`` and rebaseline, so
        the commit button goes back to disabled."""
        if not step_id:
            # No step selected: the button is disabled and auto-commit is not
            # due, so only a stray call lands here.
            return

        params = self.model.routes._current_params()
        logger.info(f"Committing execution settings to step {step_id}: {params}")

        message = StepParamsCommitMessage(step_id=step_id, **params)
        publish_message(topic=STEP_PARAMS_COMMIT, message=message.serialize())

        self.model.routes.mark_params_committed()

    @observe("model:commit_requested")
    def _on_commit_requested(self, event):
        self._commit_sidebar_params(self._last_applied_step_id)

    @observe("model:auto_commit_due")
    def _schedule_auto_commit(self, event):
        """Restart the quiet period on each edit while auto-commit is due;
        drop a pending commit once it is not (protocol started, toggle off,
        values back to the step's)."""
        if event.new:
            self._auto_commit_timer.start()
        else:
            self._auto_commit_timer.stop()

    def _auto_commit_sidebar_params(self):
        # The gate is read again: the step or the run state may have changed
        # since the edit that started the timer.
        if self.model.auto_commit_due:
            self._commit_sidebar_params(self._last_applied_step_id)

    # --------------UI view content creation / configuration helpers ---------
    def set_interaction_service(self, new_model):
        """Handle when the electrodes model changes."""
        logger.debug(
            f"New Electrode Layer added --> {new_model.electrodes.svg_model.filename}"
        )

        # The old interaction service's zone overlays sit on the old scene.
        if self.scene.interaction_service is not None:
            self.scene.interaction_service.cleanup()

        # One stepping service per loaded device, shared by the keyboard
        # handlers and the layers (LayerContext.stepping), so every input
        # moves the same electrode cursor.
        stepping = ElectrodeSteppingService(model=new_model)

        # Initialize the electrode mouse / key interaction service with the
        # new model and layer
        interaction_service = ElectrodeInteractionControllerService(
            model=new_model,
            electrode_view_layer=self.current_electrode_layer,
            device_view=self.device_view,
            device_viewer_preferences=self.device_viewer_preferences,
            stepping=stepping,
        )
        interaction_service.keyboard = KeyboardShortcutService(
            model=new_model,
            stepping=stepping,
            interaction=interaction_service,
            device_view=self.device_view,
            undo_handler=self.undo,
            redo_handler=self.redo,
            show_shortcuts_handler=partial(
                show_keyboard_shortcuts,
                KEYBOARD_SHORTCUTS,
                KEYBOARD_SHORTCUT_GROUPS,
                KEYBOARD_SHORTCUTS_TITLE,
            ),
        )

        # Update the scene with the interaction service
        self.scene.interaction_service = interaction_service
        self.scene.interaction_service.electrode_state_recolor(None)
        # Paint the white "possible connections" base layer for the freshly
        # loaded device.
        self.scene.interaction_service.route_redraw(None)
        # Regions restored from the SVG's Zones layer.
        self.scene.interaction_service.zones_redraw(None)

        logger.debug(
            f"Setting up handlers for new layer for new electrodes model {new_model}"
        )

    def remove_current_layer(self):
        """
        Utility methods to remove current scene's electrode layer.
        """
        if self.current_electrode_layer:
            self.current_electrode_layer.remove_all_items_to_scene(self.scene)

    def configure_camera_to_scene_size(self):
        ##### Size #####
        scene_rect = self.scene.sceneRect()
        video_size = QSizeF(scene_rect.width(), scene_rect.height())
        self.video_item.setSize(video_size)

        ### define default perspective rectangle for video framing ############
        x, y = scene_rect.center().toTuple()
        w, h = scene_rect.size().toTuple()
        w, h = w / 4, h / 4
        self.model.camera_perspective.default_rect = [
            QPointF(x - w, y - h),
            QPointF(x + w, y - h),
            QPointF(x + w, y + h),
            QPointF(x - w, y + h),
        ]  # bounding_box
        if len(self.model.camera_perspective.reference_rect) != 4:
            # force update so rotation is shown
            self.model.camera_perspective.update_transformation()

    def set_view_from_model(self, new_electrodes_model: "Electrodes"):
        self.remove_current_layer()

        # use model method to figure out default alpha values taking into
        # account visible settings.
        default_alphas = {
            key: self.model.get_alpha(key)
            for key in self.device_viewer_preferences.default_alphas
        }

        # create new electrode layer and add to scene
        self.current_electrode_layer = ElectrodeLayer(
            new_electrodes_model, default_alphas
        )
        self.current_electrode_layer.add_all_items_to_scene(self.scene)

        # Fit the View
        self.device_view.resetTransform()

        layer_bounding_rect = (
            self.current_electrode_layer.get_electrodes_views_bounding_rect()
        )

        if layer_bounding_rect and not layer_bounding_rect.isEmpty():
            # Update the scene's boundary to match the new focus area
            self.scene.setSceneRect(layer_bounding_rect)

            self.device_view.fit_to_scene_rect()

        # recenter the camera to the new device scale
        if self.video_item:
            self.configure_camera_to_scene_size()

    def _initialize_svg_view(self):
        # A different device has a different saved endpoint — close the
        # old device's alignment dialog before rebuilding the view.
        self.camera_alignment_controller.close_alignment_dialog()
        self._close_connections_editor()

        # Trigger an update to redraw and re-initialize view using model.
        self.set_view_from_model(self.model.electrodes)

        # Initialize service to handle user interactions.
        self.set_interaction_service(self.model)
        logger.info(f"Electrodes model set to {self.model}")

        if self.layer_host is not None:
            self.layer_host.device_loaded(self.scene.interaction_service.stepping)

        # The video item now spans the new device's scene: restore the
        # camera alignment saved for this camera on this device.
        self.camera_alignment_controller.device_loaded()

    def _set_device_view_from_svg(self, svg_file=None):
        """Load a device into the model now; rebuild the view from it only
        once the view is built (its build shows the loaded device)."""

        if self.device_loader.load(svg_file) and self.device_view_built:
            self._initialize_svg_view()

    # --------------------- UI initialization -----------------------

    @observe(
        "device_viewer_preferences:[DEVICE_VIEWER_SIDEBAR_WIDTH, "
        "ALPHA_VIEW_MIN_HEIGHT, LAYERS_VIEW_MIN_HEIGHT, "
        "ZONES_VIEW_MIN_HEIGHT]",
        post_init=True,
    )
    def _set_device_view_layout_width(self, event=None):

        if self.scroll_area and self.scroll_content:
            self.scroll_area.setMaximumWidth(
                self.device_viewer_preferences.DEVICE_VIEWER_SIDEBAR_WIDTH
            )
            self.scroll_content.setMaximumWidth(
                self.device_viewer_preferences.DEVICE_VIEWER_SIDEBAR_WIDTH - 5
            )  # offset to fit within the area

            # A section still loading is sized as it is built.
            for deferred in self.sidebar_builder.sections:
                if deferred.section is not None:
                    self._size_sidebar_section(deferred.section)

    def _size_sidebar_section(self, section):
        if isinstance(section, SizedSidebarSection):
            section.apply_sizes(self.device_viewer_preferences)

    def create(self, parent):
        """Load the preferred device into the model, then create the pane.

        The model side comes first and at once: other plugins depend on
        the loaded device and the messages announcing it, whether or not
        the view is built yet.
        """
        self._set_up_device_model()

        super().create(parent)

    def _set_up_device_model(self):
        """Load the preferred device, publish the first state message, and
        follow zone edits — everything but the view."""
        self.device_loader.load()

        self.publish_controller.publish_model_message(event=None)

        # Zone edits reach the model before the Zones section is built.
        self.zones_controller = ZonesController(model=self.model)

    def create_contents(self, parent):
        """Build the view from the loaded model."""
        logger.debug("creating device viewer dock pane contents")

        if self.device_loader.device_loaded:
            self._initialize_svg_view()

        ###################################################################
        # Initialize camera primitives
        ###################################################################
        self.video_item = QGraphicsVideoItem()
        self.video_item.setZValue(
            -100
        )  # Set a low z-value to ensure the video is behind other items
        self.video_item.setOpacity(self.model.get_alpha("video"))

        ################### Determine Size for video #####################
        self.configure_camera_to_scene_size()

        # The alignment presets follow the feed's size.
        self.video_item.nativeSizeChanged.connect(self._on_camera_frame_size_changed)
        self._on_camera_frame_size_changed(self.video_item.nativeSize())

        # Only the viewport controls now; the other sections show their
        # loading line until they are built, after the first paint.
        self.sidebar_sections = [
            build_viewport_controls(self.model),
            *self.sidebar_builder.sections,
        ]
        self.scroll_area = build_sidebar(self.sidebar_sections)
        self.scroll_content = self.scroll_area.widget()
        self._set_device_view_layout_width()

        self.layer_host = self._build_layer_host()

        self.reveal_button = build_reveal_button(self.scroll_area)

        # Device view on the left, the sidebar and its reveal toggle on the right.
        main_layout = QHBoxLayout()
        main_layout.addWidget(self.device_view, 1)
        main_layout.addWidget(self.reveal_button)
        main_layout.addWidget(self.scroll_area)

        main_container = QWidget()
        main_container.setLayout(main_layout)

        for widget in (self.scroll_content, self.reveal_button):
            widget.setContextMenuPolicy(Qt.CustomContextMenu)
            widget.customContextMenuRequested.connect(self._show_sidebar_context_menu)

        self._apply_theme_style(
            theme=Qt.ColorScheme.Dark if is_dark_mode() else Qt.ColorScheme.Light
        )
        QApplication.styleHints().colorSchemeChanged.connect(self._apply_theme_style)

        # style device view: remove frame in device view
        self.device_view.setFrameStyle(QFrame.NoFrame)

        self.device_view_built = True

        # The sections follow on paced turns, the pane's contents first on
        # screen; built behind a tab (for a camera request), they follow
        # all the same.
        self.sidebar_builder.start()

        return main_container

    def _create_sidebar_builder(self):
        """Set up the sidebar sections built after the pane's own build, top
        to bottom, so content already in never moves (#1064)."""
        self._camera_controls_section = DeferredSidebarSection(
            title="Camera Controls", build=self._build_camera_controls
        )
        self.sidebar_builder = SidebarSectionBuilder(
            sections=[
                self._camera_controls_section,
                DeferredSidebarSection(
                    title="Paths",
                    build=partial(build_paths, self.model, self.undo, self.redo),
                ),
                DeferredSidebarSection(
                    title="Zones", build=partial(build_zones, self.model)
                ),
                DeferredSidebarSection(
                    title="Calibration",
                    build=partial(build_calibration, self.model.calibration),
                ),
            ]
        )

        # Registered first, so each section is wired into the pane before
        # any request waiting on it runs.
        for deferred in self.sidebar_builder.sections:
            self.sidebar_builder.when_built(deferred, self._size_sidebar_section)

        self.sidebar_builder.when_built(
            self._camera_controls_section, self._attach_camera_controls
        )

    def _build_camera_controls(self):
        return build_camera_controls(
            self.model,
            self.video_item,
            self.scene,
            self.app_preferences,
            source_providers=self._camera_source_providers,
            on_align_camera=self.camera_alignment_controller.open_camera_alignment,
            on_go_to_endpoint=self.camera_alignment_controller.go_to_endpoint,
        )

    def _attach_camera_controls(self, section):
        """The camera panel exists: requests reach it, and the alignment
        controller takes charge of the live alignment per camera."""
        self.camera_control_widget = section.camera_control_widget
        self.camera_alignment_controller.camera_model = (
            self.camera_control_widget.camera_model
        )
        self._connect_recording_icon()

    def when_camera_controls_built(self, on_built, on_failed=None):
        """Call ``on_built(camera_control_widget)`` now, or once the Camera
        Controls section is built; ``on_failed(error)`` instead if it, or
        the pane, fails to build. GUI thread only.

        Builds the pane if it is not yet: a protocol's camera step must not
        wait for the pane to be shown.
        """

        def wait_on_camera_section(contents):
            self.sidebar_builder.when_built(
                self._camera_controls_section,
                lambda section: on_built(section.camera_control_widget),
                on_failed,
            )

        self.when_content_built(wait_on_camera_section, on_failed)

        self.ensure_built()

    def _build_layer_host(self):
        """Mount the contributed layers on this pane, below the sidebar."""
        # A default device that failed to load leaves no interaction service
        # (the load error was already reported); layers then get stepping on
        # the first successful load, via LayerHost.device_loaded.
        interaction_service = getattr(self.scene, "interaction_service", None)
        stepping = getattr(interaction_service, "stepping", None)

        context = LayerContext(
            model=self.model,
            scene=self.scene,
            device_view=self.device_view,
            undo_stack=self.undo_manager.active_stack,
            preferences=self.app_preferences,
            status_bar_manager=self.task.window.status_bar_manager,
            stepping=stepping,
        )
        layer_host = LayerHost(context=context, sidebar=self.scroll_area)

        try:
            factories = self.task.window.application.get_extensions(
                DEVICE_VIEWER_LAYERS
            )
        except Exception:
            logger.warning("Device viewer layer extension point unavailable")
            factories = []

        layer_host.add_layers(factories)

        return layer_host

    @observe("task:window:status_bar_manager")
    def _share_status_bar_with_layers(self, event):
        """The task creates the status bar after this pane; pass it on."""
        if self.layer_host is not None:
            self.layer_host.context.status_bar_manager = event.new

    def destroy(self):
        """Detach the contributed layers before the pane's widgets go."""
        if self.layer_host is not None:
            self.layer_host.remove_all()

        if self.calibration_reminder is not None:
            self.calibration_reminder.stop()

        super().destroy()

    def _show_sidebar_context_menu(self, point):
        """Offer the sidebar layout preferences at the right-clicked point."""
        menu = QMenu(self.scroll_content)
        settings_action = menu.addAction("Modify Layout...")
        settings_action.triggered.connect(self._open_sidebar_layout_settings)

        menu.exec(self.scroll_content.mapToGlobal(point))

    def _open_sidebar_layout_settings(self):
        """Open the sidebar layout preferences, or raise the open editor."""
        if self.edit_sidebar_layout_ui:
            control = self.edit_sidebar_layout_ui.control

            if control:
                if control.isVisible():
                    control.raise_()
                    control.activateWindow()

                return

            # The editor's widget was destroyed while its UI lingered.
            self.edit_sidebar_layout_ui = None

        self.edit_sidebar_layout_ui = self.device_viewer_preferences.edit_traits(
            view=View(sidebar_settings_grid, resizable=True)
        )

    def _apply_theme_style(self, theme):
        """Restyle the sidebar and device view for the application theme."""
        theme_name = QT_THEME_NAMES[theme]

        logger.debug(f"Applying {theme_name} mode")

        self.scroll_area.setStyleSheet(get_complete_stylesheet(theme_name))

        # The device view renders through OpenGL, so it cannot take the full
        # widget stylesheet; only its tooltips need the theme.
        self.device_view.setStyleSheet(get_tooltip_style(theme_name))
        self.device_view.setBackgroundBrush(QBrush(QColor(BLACK)))

        self.reveal_button.setStyleSheet(
            get_complete_stylesheet(theme_name, button_type="narrow")
        )

    ###################################################################################################################
    ###### SVG file loading / saving / other handling ########
    ###################################################################################################################

    def _proceed_despite_unsaved_changes(self):
        """Ask before discarding unsaved device edits; True to go ahead."""

        if not self.svg_persistence.modified:
            return True

        user_choice = confirm(
            None,
            "Current device svg has unsaved changes.\nProceed without saving?",
            title="Unsaved Device SVG Changes",
            cancel=False,
        )

        if user_choice == NO:
            logger.warning("Action cancelled due to unsaved changes.")

            return False

        return True

    @app_statusbar_message_from_dock_pane("...Loading Svg")
    def load_default_svg(self):
        """Load the bundled default device."""
        if self._proceed_despite_unsaved_changes():
            self._set_device_view_from_svg(str(MASTER_SVG_FILE))

    @app_statusbar_message_from_dock_pane("...Loading Svg")
    def load_svg_dialog(self):

        # -- 0. Make sure user saves existing changes if file modified:

        if not self._proceed_despite_unsaved_changes():
            return

        # --- 1. Open a dialog for the user to select a source file ---
        # This is decoupled from self.file to allow loading any file at any time.
        default_path = self.device_viewer_preferences.DEFAULT_SVG_FILE

        # Browse the user's devices rather than the install's resources folder.
        if is_bundled_device(default_path):
            default_path = self.device_viewer_preferences.DEVICE_REPO_DIR

        dialog = FileDialog(
            action="open",
            default_path=str(default_path),
            wildcard="SVG Files (*.svg)|*.svg|All Files (*.*)|*.*",
        )

        if dialog.open() != OK:
            logger.info("File selection cancelled by user.")
            return None

        src_file = Path(dialog.path)
        repo_dir = Path(self.device_viewer_preferences.DEVICE_REPO_DIR)

        # --- 3. Handle case where the selected file is already in the repo ---
        # We just select it in the UI and do not need to copy anything. A
        # bundled device is loaded in place too: it is read-only.
        logger.debug("Checking for chosen file in repo...")

        if src_file.parent == repo_dir or is_bundled_device(src_file):
            logger.debug(
                f"File '{src_file.name}' is in the repo or bundled. Selecting it."
            )
            self._set_device_view_from_svg(src_file)
            return OK

        logger.info("\n--- Loading external svg file into device repo ---")

        dst_file = Path(repo_dir) / src_file.name

        if not dst_file.exists():
            # --- 4a. No conflict: The file doesn't exist, copy it directly.

            self._set_device_view_from_svg(safe_copy_file(src_file, dst_file))

            logger.info(
                f"{dst_file.name} has been copied to {src_file.name}. It was "
                f"not found in the repo before."
            )

            return OK

        else:
            # --- 4b. Conflict: File exists. Ask the user what to do. ---
            logger.info(f"File '{dst_file.name}' already exists. Confirm Overwriting.")

            confirm_overwrite = confirm(
                parent=None,
                message=f"A file named '{dst_file.name}' already exists in "
                "the repository. What would you like to do?",
                title="Warning: File Already Exists",
                cancel=True,
                yes_label="Overwrite",
                no_label="Save As...",
            )

            if confirm_overwrite == YES:
                # --- Overwrite the existing file ---
                logger.debug(f"User chose to overwrite '{dst_file.name}'.")

                self._set_device_view_from_svg(safe_copy_file(src_file, dst_file))

                return OK

            elif confirm_overwrite == NO:
                # --- Open a 'Save As' dialog to choose a new name ---
                logger.debug("User chose 'Save As...'. Opening save dialog.")

                dialog = FileDialog(
                    action="save as",
                    default_directory=str(repo_dir),
                    default_filename=src_file.stem + " - Copy",
                    wildcard="SVG Files (*.svg)|*.svg",
                )

                ###### Handle Save As Dialog ######################
                if dialog.open() == OK:
                    dst_file = dialog.path

                    self._set_device_view_from_svg(safe_copy_file(src_file, dst_file))

                    return OK

                else:
                    logger.debug("Save As dialog cancelled by user.")
                    return None

                ####################################################

            else:  # result == CANCEL
                logger.debug("Load operation cancelled by user.")
                return None

    @app_statusbar_message_from_dock_pane("...Saving Svg")
    def save_as_svg_dialog(self):
        """Open a file dialog to save the current model to an SVG file.

        A target the service refuses reopens the dialog. Saving a bundled
        device carries on with the copy, which becomes the default device.
        """
        from_bundled = self.svg_persistence.bundled_device_loaded
        default_filename = ""

        if from_bundled:
            default_filename = f"{Path(self.svg_persistence.loaded_path).stem} - Copy"

        while True:
            dialog = FileDialog(
                action="save as",
                default_directory=str(self.device_viewer_preferences.DEVICE_REPO_DIR),
                default_filename=default_filename,
                wildcard="SVG Files (*.svg)|*.svg",
            )

            if dialog.open() != OK:
                return

            try:
                written_path = self.svg_persistence.save_as(str(dialog.path))

                break

            except PermissionError as e:
                logger.warning(f"Save As refused: {e}", extra=LOG_RECORDED_EXTRA)
                warning(
                    None,
                    f"{e}<br><br>Choose another location.",
                    title="Cannot Save Device Here",
                )

        if from_bundled:
            self.device_viewer_preferences.DEFAULT_SVG_FILE = written_path

    @app_statusbar_message_from_dock_pane("...Saving Svg")
    def save_svg(self):
        if self.svg_persistence.bundled_device_loaded:
            information(
                None,
                "Bundled devices are restored on every update and cannot be "
                "overwritten. Save your edits as a copy instead.",
                title="Bundled Device",
                cancel=False,
            )
            self.save_as_svg_dialog()

            return

        self.svg_persistence.save()

    @app_statusbar_message_from_dock_pane("...Generating Connections")
    def generate_svg_connections(self):
        self.model.electrodes.svg_model.generate_connections_from_neighbouring_electrodes()

    def edit_svg_connections(self):
        """Open the Edit Connections dialog: the device SVG rendered
        alone with a dot on every electrode centroid, to drag new
        connections between and delete existing ones. Edits land on the
        SVG model directly — ``_on_connections_changed`` redraws the
        main view, and Save writes them to the file."""
        # The dialog takes the device's path scale from the built view.
        self.ensure_built()

        if self.current_electrode_layer is None:
            warning(
                None,
                "No device is loaded — load a device SVG first.",
                title="Edit Connections",
            )

            return

        image, scene_rect = self._render_device_image()

        if image is None:
            error(
                None,
                "The loaded device has no drawable geometry.",
                title="Edit Connections",
            )

            return

        self._close_connections_editor()

        self._connections_editor_ui = ConnectionsEditorPane(
            model=ConnectionsEditorModel(svg_model=self.model.electrodes.svg_model),
            device_image=image,
            scene_rect=scene_rect,
            path_scale=self.current_electrode_layer.path_scale,
            device_name=self.model.device_key,
        ).edit_traits(parent=self.device_view.window())

    #################################################################################################################
    ###### Trait Observers -- Model and Model Traits ########
    #################################################################################################################

    @observe("svg_persistence:[loaded_path, modified]")
    def _update_name_from_svg_persistence(self, event):
        """Title the pane with the loaded device, tagged while unsaved."""
        name = _dock_pane_name

        if self.svg_persistence.loaded_path:
            name += "\t\t-\t\t" + Path(self.svg_persistence.loaded_path).stem

        if self.svg_persistence.modified:
            name += device_modified_tag

        self.name = name

    @observe("model:electrodes:svg_model:connections")
    def _on_connections_changed(self, event):
        """Connections were generated or hand edited: swap the main
        view's connection items and repaint the routes over them."""
        if self.current_electrode_layer is None:
            return

        self.current_electrode_layer.rebuild_connection_items(self.scene)

        orphaned_segments = [
            segment
            for route_layer in self.model.routes.layers
            for segment in route_layer.route.get_segments()
            if segment not in event.new
        ]

        if orphaned_segments:
            logger.warning(
                f"Routes run over connections that no longer exist: {orphaned_segments}"
            )

        self.scene.interaction_service.route_redraw(None)

    # Only a channel edit on an existing electrode notifies. A device load's
    # clear() then update() would publish an empty map just before the full
    # one, and receivers can apply the two out of order.
    @observe("model:electrodes:electrodes:items:channel")
    def _on_electrode_channel_changed(self, event=None):
        """Re-publish geometry whenever any electrode's channel assignment changes
        (e.g., via channel-edit mode). Gated by _publish_geometry_if_changed."""
        if self.publish_controller._disable_state_messages:
            return
        self.publish_controller._publish_geometry_if_changed()

    @observe("model:electrodes:svg_model.svg_error_paths")
    def _svg_errors_found(self, event):
        if self.model.electrodes.svg_model.svg_error_paths:
            warning(
                None,
                modal=False,
                message=f"Could not load all electrodes from "
                f"{self.model.electrodes.svg_model.filename}:<br><br>"
                f"Error Paths: "
                f"{self.model.electrodes.svg_model.svg_error_paths}<br><br>"
                f"Errors: {self.model.electrodes.svg_model.svg_exceptions_caught}",
            )

    @observe("model.camera_perspective.transformation")
    @observe("video_item")
    def camera_perspective_change_handler(self, event):
        """Apply the camera perspective transformation to the video feed.

        The matrix maps item coordinates (the item is sized to the scene, not
        to the camera's native resolution), so it applies to any source,
        including provider cameras that never report a resolution. Observing
        the video item applies a matrix loaded from preferences before the
        item existed.
        """
        if self.video_item:
            self.video_item.setTransform(self.model.camera_perspective.transformation)

    @observe("model.alpha_map.items.[alpha, visible]", post_init=True)
    def _alpha_change(self, event):

        if isinstance(event.object, AlphaValue):
            changed_key = event.object.key

            if changed_key == video_key and self.video_item:
                self.video_item.setOpacity(self.model.get_alpha(video_key))

    @observe("model.step_label")
    @observe("model.free_mode")
    @observe("model.editable")
    @observe("model.protocol_running")
    def step_label_change(self, event):
        _status_bar_manager = self.task.window.status_bar_manager

        if _status_bar_manager:
            if self.model.protocol_running:
                _status = "Running Protocol"
                if self.model.editable:
                    _status += " (Editable)"
                _status_bar_manager.message = f"{_status}: {self.model.step_label}"

            elif self.model.step_label:
                _status_bar_manager.message = f"Editing: {self.model.step_label}"

            elif self.model.free_mode:
                _status_bar_manager.message = "Free Mode"

    @observe("model:mode")
    def _mode_changed(self, event):

        _status_bar_manager = self.task.window.status_bar_manager
        if _status_bar_manager:
            if event.new == "camera-place":
                _status_bar_manager.messages += [camera_place_status_message_text]

            if event.new == "camera-edit":
                _status_bar_manager.messages += [camera_edit_status_message_text]

            if event.old == "camera-place":
                _status_bar_manager.remove(camera_place_status_message_text)

            if event.old == "camera-edit":
                _status_bar_manager.remove(camera_edit_status_message_text)

    @observe("device_viewer_preferences:_auto_fit_margin_scale ")
    def _auto_fit_margin_scale_change(self, event):
        self.device_view.auto_fit_margin_scale = event.new

    @observe("task:window:application:extra_plugins_loaded", post_init=True)
    def _on_extra_plugins_loaded(self, event):
        """Hot-loaded plugin groups start after the camera panel is built:
        re-enumerate so their camera sources appear without a manual
        refresh."""
        if getattr(self, "camera_control_widget", None) is not None:
            self.camera_control_widget.initialize_camera_list()

    def _camera_source_providers(self):
        """Instantiate camera-source providers contributed by other plugins
        (CAMERA_SOURCES extension point). A failing factory is logged and
        skipped so a broken contribution can't take the camera panel down."""
        from device_viewer.consts import CAMERA_SOURCES

        providers = []
        try:
            factories = self.task.window.application.get_extensions(CAMERA_SOURCES)
        except Exception:
            logger.warning("Camera-source extension point unavailable")
            return providers
        for factory in factories:
            try:
                providers.append(factory())
            except Exception:
                logger.error(
                    f"Camera-source provider {factory!r} failed to construct; skipping",
                    exc_info=True,
                )
        return providers

    @observe("task:window:status_bar_manager")
    def _setup_app_statusbar(self, event):
        if getattr(self, "recording_icon", None) is not None:
            return  # already built; a re-fired manager
            # assignment must not duplicate icons

        _font = QFont(ICON_FONT_FAMILY)
        _font.setPointSize(STATUSBAR_ICON_POINT_SIZE)

        # Recording indicator: hidden until the camera's record toggle fires.
        self.recording_icon = PulsingLabel(
            icon_str="album",
            stylesheet="color: red;",
            tooltip="Recording in progress...",
        )
        self.recording_icon.setFont(_font)
        self.recording_icon.hide()
        self.recording_icon.status_bar_icon_priority = ICON_PRIORITY_LEFT
        self._connect_recording_icon()

        # Contribute the icon; the microdrop_status_bar plugin owns its
        # placement, spacing, and removal.
        plugin = self.task.window.application.get_plugin(PKG)

        if plugin is None:
            logger.warning(f"{PKG}: plugin not found; status-bar icons not shown")
            return

        plugin.status_bar_icons.append(self.recording_icon)

    def _connect_recording_icon(self):
        """Once both the recording icon and the camera panel exist, the
        record button drives the icon."""
        recording_icon = getattr(self, "recording_icon", None)

        if recording_icon is None or self.camera_control_widget is None:
            return

        widget = self.camera_control_widget

        widget.record_toggle_button.toggled.connect(recording_icon.set_enabled)
