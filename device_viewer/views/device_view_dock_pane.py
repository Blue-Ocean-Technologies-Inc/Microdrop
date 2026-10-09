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
import traceback
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
    QWidget,
)
from pyface.tasks.api import TraitsDockPane
from pyface.undo.api import CommandStack, UndoManager
from traits.api import Instance, List, observe
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
    warning,
)
from microdrop_status_bar.consts import ICON_PRIORITY_LEFT

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
from microdrop_utils.pyface_helpers import app_statusbar_message_from_dock_pane
from microdrop_utils.pyside_helpers import (
    PulsingLabel,
)

# Local imports.
from ..consts import (
    ALIGNMENT_DEVICE_RENDER_WIDTH_PX,
    DEVICE_VIEWER_LAYERS,
    PKG,
    STEP_PARAMS_COMMIT,
    ZONE_STATUS_MESSAGE_MS,
    PKG_name,
    camera_edit_status_message_text,
    camera_place_status_message_text,
    device_modified_tag,
)
from ..controllers.camera_alignment_controller import (
    CameraAlignmentWorkflowController,
)
from ..controllers.device_viewer_message_controller import (
    DeviceViewerMessageController,
)
from ..controllers.device_viewer_publish_controller import (
    DeviceViewerPublishController,
)
from ..controllers.layer_host import LayerHost
from ..default_settings import ELECTRODE_OFF, video_key
from ..interfaces.layer_context import LayerContext
from ..models.alpha import AlphaValue
from ..models.connections_editor import ConnectionsEditorModel
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
from ..services.svg_persistence_service import SvgPersistenceService
from ..utils.auto_fit_graphics_view import AutoFitGraphicsView
from .connections_editor_view.connections_editor_pane import ConnectionsEditorPane
from .electrode_view.electrode_layer import ElectrodeLayer
from .electrode_view.electrode_scene import ElectrodeScene
from .sidebar.calibration import build_calibration
from .sidebar.camera_controls import build_camera_controls
from .sidebar.host import build_reveal_button, build_sidebar
from .sidebar.paths import build_paths
from .sidebar.section import SidebarSection
from .sidebar.viewport_controls import build_viewport_controls
from .sidebar.zones import build_zones

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

_dock_pane_name = f"{PKG_name} Dock Pane"


# Debounce delay (ms) so arrow-key navigation publishes once after movement stops
# ELECTRODE_PUBLISH_DEBOUNCE_MS = 0


class DeviceViewerDockPane(TraitsDockPane):
    """
    A widget for viewing the device. This puts the electrode layer into a graphics view.
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

    layer_ui = None
    zones_ui = None

    #: Camera controls widget; None until ``create_contents`` builds it.
    camera_control_widget = None

    #: The open Edit Connections dialog; None while closed.
    _connections_editor_ui = Instance(UI)

    #: The sidebar's sections, top to bottom; holding them keeps each
    #: section's controllers and TraitsUI UIs alive with the pane.
    sidebar_sections = List(Instance(SidebarSection))

    #: The open sidebar layout preferences editor; None until opened.
    edit_sidebar_layout_ui = Instance(UI)

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

        ################################################################################################
        # ----------- Setup device view widget ----------------- #
        ################################################################################################

        self.scene = ElectrodeScene()
        self.device_view = AutoFitGraphicsView(
            self.scene,
            auto_fit_margin_scale=self.device_viewer_preferences._auto_fit_margin_scale,
        )
        self.device_view.setObjectName("device_view")

        # Owns the outbound publishing; created before the message
        # controller so its inbound handlers can already reach it.
        self.publish_controller = DeviceViewerPublishController(model=self.model)

        # Per-device saved endpoints and the combined endpoint/outline
        # alignment dialog.
        self.camera_alignment_controller = CameraAlignmentWorkflowController(
            model=self.model,
            get_video_item=lambda: self.camera_control_widget.video_item,
            get_electrode_layer=lambda: self.current_electrode_layer,
            render_device_image=self._render_device_image,
            get_dialog_parent=lambda: self.device_view.window(),
            statusbar_message=self._statusbar_message,
        )

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
        margin = 0.02 * max(rect.width(), rect.height())
        rect = rect.adjusted(-margin, -margin, margin, margin)
        height_px = max(int(width_px * rect.height() / rect.width()), 1)

        image = QImage(width_px, height_px, QImage.Format_ARGB32_Premultiplied)
        image.fill(QColor(BLACK))
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing, True)
        scene.render(painter, QRectF(0, 0, width_px, height_px), rect)
        painter.end()

        return image, rect

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

        if (
            step_changed
            and message_model.execution_params
            and not self.model.protocol_running
        ):
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
                    f"{self._last_applied_step_id}"
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
                    prev_id = self._last_applied_step_id
                    params = self.model.routes._current_params()
                    logger.info(
                        f"Sending protocol step: {prev_id} execution settings: {params}"
                    )
                    commit_msg = StepParamsCommitMessage(step_id=prev_id, **params)
                    publish_message(
                        topic=STEP_PARAMS_COMMIT, message=commit_msg.serialize()
                    )

    @observe("model:routes:commit_to_step_btn")
    def _on_commit_to_step_btn_fired(self, event):
        step_id = self._last_applied_step_id
        if not step_id:
            # No step selected — shouldn't happen because the button is disabled,
            # but guard anyway.
            return

        params = self.model.routes._current_params()
        msg = StepParamsCommitMessage(step_id=step_id, **params)
        publish_message(topic=STEP_PARAMS_COMMIT, message=msg.serialize())

        # Re-baseline so the button goes back to disabled.
        self.model.routes.mark_params_committed()

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

        # new device: reset undo manager.
        self.undo_manager.active_stack.clear()

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

        # Publish geometry after SVG is fully loaded and channel mapping is established.
        self.publish_controller._publish_geometry_if_changed()

    def _set_device_view_from_svg(self, svg_file=None):
        if svg_file is None:
            svg_file = self.device_viewer_preferences.DEFAULT_SVG_FILE

        try:
            unloaded = self.svg_persistence.load(svg_file)

            if unloaded > 0:
                warning(
                    None,
                    f"{unloaded} zone region(s) in this device file reference "
                    "electrodes that do not exist in it and were dropped or "
                    "trimmed. Saving the file will write it without those "
                    "electrodes.",
                    title="Zones Not Loaded",
                )

            self._initialize_svg_view()

            # if model and view can be set, change default svg file
            self.device_viewer_preferences.DEFAULT_SVG_FILE = svg_file

        except Exception as e:
            logger.error(
                f"Could not create electrodes from SVG file: {svg_file}. Error: {e}",
                exc_info=True,
            )
            error(
                self.control,
                f"Could not create electrodes from SVG file: {svg_file} "
                f"<br><br> Reason: {e}",
                detail="".join(traceback.format_exception(type(e), e, e.__traceback__)),
                title="Error: Cannot Load Device SVG",
            )
            return

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
            self.alpha_view_ui.control.setMinimumHeight(
                self.device_viewer_preferences.ALPHA_VIEW_MIN_HEIGHT
            )
            self.alpha_view_ui.control.setMaximumWidth(
                self.device_viewer_preferences.DEVICE_VIEWER_SIDEBAR_WIDTH
            )
            self.layer_ui.control.setMinimumHeight(
                self.device_viewer_preferences.LAYERS_VIEW_MIN_HEIGHT
            )
            self.zones_ui.get_editors("zone_types")[0].control.setMinimumHeight(
                self.device_viewer_preferences.ZONES_VIEW_MIN_HEIGHT
            )

    def create_contents(self, parent):
        """Called when the task is activated."""
        logger.debug("creating device viewer dock pane contents")
        self._set_device_view_from_svg()

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

        self.publish_controller.publish_model_message(event=None)

        self.device_view.display_state_signal.connect(self.apply_message_model)

        self.sidebar_sections = self._build_sidebar_sections()
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

        return main_container

    def _build_sidebar_sections(self):
        """Build the sidebar sections, top to bottom."""
        viewport_section = build_viewport_controls(self.model)

        # status_bar_manager is typically None at create_contents time (the
        # MicrodropTask creates it in activated(), which runs after dock pane
        # creation). _setup_app_statusbar below re-pushes the manager once
        # the trait fires.
        camera_section = build_camera_controls(
            self.model,
            self.video_item,
            self.scene,
            self.app_preferences,
            status_bar_manager=self.task.window.status_bar_manager,
            source_providers=self._camera_source_providers,
            on_align_camera=self.camera_alignment_controller.open_camera_alignment,
            on_go_to_endpoint=self.camera_alignment_controller.go_to_endpoint,
        )
        paths_section = build_paths(self.model, undo=self.undo, redo=self.redo)
        zones_section = build_zones(self.model)
        calibration_section = build_calibration(self.model.calibration)

        self.camera_control_widget = camera_section.camera_control_widget
        self.alpha_view_ui = camera_section.alpha_view_ui
        self.layer_ui = paths_section.layer_ui
        self.zones_ui = zones_section.zones_ui

        return [
            viewport_section,
            camera_section,
            paths_section,
            zones_section,
            calibration_section,
        ]

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

    @app_statusbar_message_from_dock_pane("...Loading Svg")
    def load_svg_dialog(self):

        # -- 0. Make sure user saves existing changes if file modified:

        if self.svg_persistence.modified:
            ### Open a confirmation dialog ####
            user_choice = confirm(
                None,
                "Current device svg has unsaved changes.\nProceed without saving?",
                title="Unsaved Device SVG Changes",
                cancel=False,
            )

            # 3. If user says NO, stop here. Do not run the function.
            if user_choice == NO:
                logger.warning("Action cancelled due to unsaved changes.")
                return

        # --- 1. Open a dialog for the user to select a source file ---
        # This is decoupled from self.file to allow loading any file at any time.
        dialog = FileDialog(
            action="open",
            default_path=str(self.device_viewer_preferences.DEFAULT_SVG_FILE),
            wildcard="SVG Files (*.svg)|*.svg|All Files (*.*)|*.*",
        )

        if dialog.open() != OK:
            logger.info("File selection cancelled by user.")
            return None

        src_file = Path(dialog.path)
        repo_dir = Path(self.device_viewer_preferences.DEVICE_REPO_DIR)

        # --- 3. Handle case where the selected file is already in the repo ---
        # We just select it in the UI and do not need to copy anything.
        logger.debug("Checking for chosen file in repo...")
        if src_file.parent == repo_dir:
            logger.debug(
                f"File '{src_file.name}' is already in the repo. Selecting it."
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
        """Open a file dialog to save the current model to an SVG file."""
        dialog = FileDialog(
            action="save as",
            default_directory=str(self.device_viewer_preferences.DEVICE_REPO_DIR),
            wildcard="SVG Files (*.svg)|*.svg",
        )

        if dialog.open() == OK:
            self.svg_persistence.save_as(str(dialog.path))

    @app_statusbar_message_from_dock_pane("...Saving Svg")
    def save_svg(self):
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

        # Push the manager to the camera widget now that it exists, so
        # media-capture notifications can use it directly.
        self.camera_control_widget.status_bar_manager = event.new

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
        self.camera_control_widget.record_toggle_button.toggled.connect(
            self.recording_icon.set_enabled
        )

        # Contribute the icon; the microdrop_status_bar plugin owns its
        # placement, spacing, and removal.
        plugin = self.task.window.application.get_plugin(PKG)

        if plugin is None:
            logger.warning(f"{PKG}: plugin not found; status-bar icons not shown")
            return

        plugin.status_bar_icons.append(self.recording_icon)
