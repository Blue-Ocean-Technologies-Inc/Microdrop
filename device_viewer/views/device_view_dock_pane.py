# Site package imports
from pathlib import Path

import dramatiq

from traits.api import Instance, observe, Str, Float
from traits.observation.events import ListChangeEvent, TraitChangeEvent, DictChangeEvent

from pyface.api import FileDialog, OK, confirm, YES, NO
from pyface.qt.QtGui import QGraphicsScene, QGraphicsPixmapItem, QTransform
from pyface.qt.QtOpenGLWidgets import QOpenGLWidget
from pyface.qt.QtWidgets import QWidget, QHBoxLayout, QVBoxLayout, QApplication, QSizePolicy, QLabel, QFrame, QPushButton
from pyface.qt.QtCore import Qt, QTimer, QPointF, QSizeF
from pyface.tasks.api import TraitsDockPane
from pyface.undo.api import UndoManager, CommandStack
from pyface.qt.QtMultimediaWidgets import QGraphicsVideoItem
from pyface.qt.QtMultimedia import QMediaCaptureSession

from PySide6.QtWidgets import QScrollArea


# TODO: maybe get these from an extension point for very granular control

# For sidebar
from device_viewer.utils.camera import qtransform_deserialize
from device_viewer.views.alpha_view.alpha_table import alpha_table_view
from device_viewer.views.calibration_view.widget import CalibrationView
from device_viewer.views.camera_control_view.widget import CameraControlWidget
from device_viewer.views.mode_picker.widget import ModePicker

# Device Viewer electrode and route views
from device_viewer.views.electrode_view.electrode_scene import ElectrodeScene
from device_viewer.views.electrode_view.electrode_layer import ElectrodeLayer
from device_viewer.views.route_selection_view.route_selection_view import RouteLayerView
from microdrop_utils.file_handler import safe_copy_file

# local imports
from ..models.electrodes import Electrodes
from ..preferences import DeviceViewerPreferences
from ..utils.auto_fit_graphics_view import AutoFitGraphicsView
from ..utils.message_utils import gui_models_to_message_model
from ..models.messages import DeviceViewerMessageModel
from ..consts import listener_name

# utils imports
from microdrop_utils._logger import get_logger
from microdrop_utils.pyside_helpers import CollapsibleVStackBox
from microdrop_utils.dramatiq_controller_base import basic_listener_actor_routine, generate_class_method_dramatiq_listener_actor
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_utils.timestamped_message import TimestampedMessage
from device_viewer.utils.commands import TraitChangeCommand, ListChangeCommand, DictChangeCommand
from device_viewer.utils.dmf_utils import channels_to_svg

# models and services
from device_viewer.models.main_model import DeviceViewMainModel
from device_viewer.models.route import Route
from device_viewer.consts import PKG, PKG_name
from device_viewer.services.electrode_interaction_service import ElectrodeInteractionControllerService

# ext consts
from dropbot_controller.consts import ELECTRODES_STATE_CHANGE, DETECT_DROPLETS
from protocol_grid.consts import CALIBRATION_DATA, DEVICE_VIEWER_STATE_CHANGED
from microdrop_style.button_styles import get_complete_stylesheet
from microdrop_application.application import is_dark_mode


import json

logger = get_logger(__name__, level="DEBUG")


class DeviceViewerDockPane(TraitsDockPane):
    """
    A widget for viewing the device. This puts the electrode layer into a graphics view.
    """

    # ----------- Device View Pane traits ---------------------

    undo_manager = Instance(UndoManager)

    model = Instance(DeviceViewMainModel)

    id = PKG + ".dock_pane"
    name = PKG_name + " Dock Pane"

    # Views
    scene = Instance(QGraphicsScene) 
    device_view = Instance(AutoFitGraphicsView)
    current_electrode_layer = Instance(ElectrodeLayer, allow_none=True)
    layer_ui = None
    mode_picker_view = None

    # Readings
    last_capacitance = Float()  # Last capacitance reading (in pF)

    # Variables
    _undoing = False # Used to prevent changes made in undo() and redo() from being added to the undo stack
    _disable_state_messages = False # Used to disable state messages when the model is being updated, to prevent infinite loops
    message_buffer = Str() # Buffer to hold the message to be sent when the debounce timer expires
    video_item = None  # The video item for the camera feed
    opencv_pixmap = None  # Pixmap item for OpenCV images
    debounce_timer = None  # Timer to debounce state messages

    dramatiq_listener_actor = Instance(dramatiq.Actor)

    # --------- Dramatiq Init ------------------------------
    def listener_actor_routine(self, message, topic):
        return basic_listener_actor_routine(self, message, topic)

    # --------- Device View trait initializers -------------
    def traits_init(self):
        logger.info("Starting DeviceViewer listener")
        self.dramatiq_listener_actor = generate_class_method_dramatiq_listener_actor(
            listener_name=listener_name,
            class_method=self.listener_actor_routine)

        self.app_preferences = self.task.window.application.preferences_helper.preferences
        self.device_viewer_preferences = DeviceViewerPreferences(preferences=self.app_preferences)

        self.undo_manager = UndoManager(active_stack=CommandStack())
        self.undo_manager.active_stack.undo_manager = self.undo_manager

        self.model = DeviceViewMainModel(undo_manager=self.undo_manager)

        if not Path(self.device_viewer_preferences.DEFAULT_SVG_FILE).exists():
            self.device_viewer_preferences.reset_traits(["DEFAULT_SVG_FILE"])

        self.model.electrodes.set_electrodes_from_svg_file(self.device_viewer_preferences.DEFAULT_SVG_FILE)


        # Load preferences to model
        transform = self.app_preferences.get("camera.transformation")
        if transform: # If preference exists
            self.model.camera_perspective.transformation = qtransform_deserialize(transform)

        self.scene = ElectrodeScene(self)

        self.device_view = AutoFitGraphicsView(self.scene)
        self.device_view.setObjectName('device_view')
        self.device_view.setViewport(QOpenGLWidget())
        
        # Connect to application palette changes for theme updates
        QApplication.instance().paletteChanged.connect(self._on_application_palette_changed)
    
    def _on_application_palette_changed(self):
        """Handle application palette changes for theme updates"""
        try:
            theme = "dark" if is_dark_mode() else "light"
            self._update_theme_styling(theme)
        except Exception as e:
            logger.debug(f"Error handling palette change: {e}")
    
    def _apply_initial_theme_styling(self):
        """Apply initial theme styling when the UI is first built"""
        try:
            theme = "dark" if is_dark_mode() else "light"
            logger.info(f"Applying initial theme styling: {theme} mode")
            self._update_theme_styling(theme)
        except Exception as e:
            logger.debug(f"Error applying initial theme: {e}")
            # Fallback to light theme
            self._update_theme_styling("light")

    def _update_theme_styling(self, theme):
        """Update theme styling for all child components"""
        if hasattr(self, "device_view"):
            self.device_view.setStyleSheet(get_complete_stylesheet(theme))

        if hasattr(self, 'mode_picker_view'):
            self.mode_picker_view.update_theme_styling(theme)
        if hasattr(self, 'camera_control_widget'):
            self.camera_control_widget.update_theme_styling(theme)
        if hasattr(self, 'calibration_view'):
            self.calibration_view.update_theme_styling(theme)

        # Update section label styling based on theme
    #     section_style = self._get_section_label_style(theme)
    #     button_style = self._get_camera_button_style(theme)
    #
    #     for i in range(self.left_stack.count()):
    #         widget = self.left_stack.widget(i)
    #         if isinstance(widget, QLabel) and widget.text() in ["Camera Controls", "Capacitance Calibration", "Paths"]:
    #             widget.setStyleSheet(section_style)
    #
    #     # Update camera control buttons if they exist
    #     if hasattr(self, 'camera_controls_container'):
    #         for child in self.camera_controls_container.findChildren(QPushButton):
    #             child.setStyleSheet(button_style)
    #
    # def _get_section_label_style(self, theme):
    #     """Get section label styling based on theme"""
    #     if theme == "dark":
    #         return """
    #             QLabel {
    #                 color: #CCCCCC;
    #                 font-size: 12px;
    #                 font-weight: bold;
    #                 padding: 4px 0px 2px 0px;
    #                 margin-bottom: 4px;
    #             }
    #         """
    #     else:  # light theme
    #         return """
    #             QLabel {
    #                 color: #333333;
    #                 font-size: 12px;
    #                 font-weight: bold;
    #                 padding: 4px 0px 2px 0px;
    #                 margin-bottom: 4px;
    #             }
    #         """
    #
    # def _get_camera_button_style(self, theme):
    #     """Get camera control button styling based on theme"""
    #     if theme == "dark":
    #         return """
    #             QPushButton {
    #                 background-color: #444444;
    #                 border: 1px solid #666666;
    #                 border-radius: 4px;
    #                 font-family: "Material Symbols Outlined";
    #                 font-size: 16px;
    #                 color: #FFFFFF;
    #             }
    #             QPushButton:hover {
    #                 background-color: #555555;
    #             }
    #         """
    #     else:  # light theme
    #         return """
    #             QPushButton {
    #                 background-color: #E0E0E0;
    #                 border: 1px solid #CCCCCC;
    #                 border-radius: 4px;
    #                 font-family: "Material Symbols Outlined";
    #                 font-size: 16px;
    #                 color: #333333;
    #             }
    #             QPushButton:hover {
    #                 background-color: #D0D0D0;
    #             }
    #         """

    # ------- Dramatiq handlers ---------------------------
    def _on_chip_inserted(self, message):
        if message == "True" and self.model:
            self.message_buffer = gui_models_to_message_model(self.model).serialize()
            self.publish_model_message()

    def _on_display_state_triggered(self, message_model_serial: str):
        # We send the message through a signal since Dramatiq runs the callbacks in a separate thread
        # Which has weird side effects on QtGraphicsObject calls
        if self.model and self.device_view:
            self.device_view.display_state_signal.emit(message_model_serial)

    def _on_state_changed_triggered(self, message: TimestampedMessage):
        """
        Handle state changes from the device viewer.
        """
        logger.debug(f"Device viewer state changed: {message}")
        if self.model and self.device_view:
            self.device_view.display_state_signal.emit(message)

    def _on_capacitance_updated_triggered(self, message):
        """
        Handle capacitance updates from the device viewer.
        """
        capacitance_str = json.loads(message).get('capacitance', None)
        if capacitance_str is not None:
            capacitance = float(capacitance_str.split("pF")[0])
            self.last_capacitance = capacitance

    def _on_screen_capture_triggered(self, message):
        """
        Handle screen capture events from the device viewer.
        """
        logger.debug(f"Screen capture triggered: {message}")
        if self.model and self.camera_control_widget:
            capture_data = None
            if message and message.strip():
                try:
                    capture_data = json.loads(message)
                except (json.JSONDecodeError, TypeError):
                    logger.debug("Screen capture message is not JSON, using default capture")
            
            self.camera_control_widget.screen_capture_signal.emit(capture_data)

    def _on_screen_recording_triggered(self, message):
        """
        Handle screen recording events from the device viewer.
        """
        logger.debug(f"Screen recording triggered: {message}")
        if self.model and self.camera_control_widget:
            recording_data = None
            if message and message.strip():
                try:
                    recording_data = json.loads(message)
                    if isinstance(recording_data, dict):
                        action = recording_data.get("action", "").lower()
                        if action in ["start", "stop"]:
                            self.camera_control_widget.screen_recording_signal.emit(recording_data)
                        else:
                            is_start = message.lower() == "true"
                            self.camera_control_widget.screen_recording_signal.emit({"action": "start" if is_start else "stop"})
                    else:
                        is_start = message.lower() == "true"
                        self.camera_control_widget.screen_recording_signal.emit({"action": "start" if is_start else "stop"})
                except (json.JSONDecodeError, TypeError):
                    is_start = message.lower() == "true"
                    self.camera_control_widget.screen_recording_signal.emit({"action": "start" if is_start else "stop"})

    def _on_camera_active_triggered(self, message):
        """
        Handle camera activation events from the device viewer.
        """
        logger.debug(f"Camera activation triggered: {message}")
        if self.model and self.camera_control_widget:
            self.camera_control_widget.camera_active_signal.emit(message.lower() == "true")

    def _on_drops_detected_triggered(self, message):
        message_obj = json.loads(message)

        detected_channels = message_obj.get("detected_channels", None)

        if detected_channels:
            detected_channels = {channel: True for channel in detected_channels}

            # Apply electrode on/off states
            self.model.electrodes.channels_states_map.update(detected_channels)

    # ------- Device View class methods -------------------------
    def set_interaction_service(self, new_model):
        """Handle when the electrodes model changes."""

        # Trigger an update to redraw and re-initialize the svg widget once a new svg file is selected.
        self.set_view_from_model(new_model.electrodes)
        logger.debug(f"New Electrode Layer added --> {new_model.electrodes.svg_model.filename}")

        # Initialize the electrode mouse interaction service with the new model and layer
        interaction_service = ElectrodeInteractionControllerService(
            model=new_model,
            electrode_view_layer=self.current_electrode_layer,
            application=self.task.window.application
        )

        # Update the scene with the interaction service
        self.scene.interaction_service = interaction_service
        self.scene.interaction_service.electrode_state_recolor(None)

        logger.debug(f"Setting up handlers for new layer for new electrodes model {new_model}")


    def remove_current_layer(self):
        """
        Utility methods to remove current scene's electrode layer.
        """
        if self.current_electrode_layer:
            self.current_electrode_layer.remove_all_items_to_scene(self.scene)

    def add_traits_event_to_undo_stack(self, event):
        command = None
        if isinstance(event, TraitChangeEvent):
            command = TraitChangeCommand(event=event)
        elif isinstance(event, ListChangeEvent):
            command = ListChangeCommand(event=event)
        elif isinstance(event, DictChangeEvent):
            command = DictChangeCommand(event=event)
        self.undo_manager.active_stack.push(command)

    @observe("model.camera_perspective.transformed_reference_rect.items, model.camera_perspective.reference_rect.items")
    @observe("model.alpha_map.items.alpha")  # Observe changes to alpha values
    def model_change_handler_with_timeout(self, event=None):
        if not self._undoing:
            self.add_traits_event_to_undo_stack(event)
            if not self.model.editable:
                self.undo() # Revert changes if not editable
                return

    @observe("model") # When the entire electrodes model is reassigned. Note that the route_manager model should never be reassigned (because of TraitsUI)
    @observe("model.routes.layers.items.route.route.items") # When a route is modified
    @observe("model.routes.layers.items") # When an electrode changes state
    @observe("model.electrodes.electrodes.items.channel") # When a electrode's channel is modified (i.e. using channel-edit mode)
    @observe("model.electrodes.channels_states_map.items") # When an electrode changes state
    @observe("model.electrodes.electrode_editing") # When an electrode is being edited
    def model_change_handler_with_message(self, event=None):
        """
        Handle changes to the model and send a message to the device viewer state change topic.
        """
        self.model_change_handler_with_timeout(event)
        if not self._disable_state_messages and self.debounce_timer:
            self.message_buffer = gui_models_to_message_model(self.model).serialize()
            logger.info(f"Buffering message for device viewer state change: {self.message_buffer}")
            self.debounce_timer.start(200) # Start timeout for sending message
    
    @observe("model.electrodes.channels_states_map.items") # When an electrode changes state
    def electrode_click_handler(self, event=None):
        if self.model.free_mode: # Only send electrode updates if we are in free mode (no step_id)
            logger.info("Sending electrode update")
            self.publish_electrode_update()
            logger.info("Electrode update sent")

    @observe("model.liquid_capacitance_over_area, model.filler_capacitance_over_area, model.electrode_scale")
    def calibration_change_handler(self, event=None):
        """
        Handle changes to the calibration values and publish a message.
        """
        self.publish_calibration_message()
        logger.info("Calibration message published")

    def undo(self):
        self._undoing = True # We need to prevent the changes made in undo() from being added to the undo stack
        self.model.undo_manager.undo()
        self._undoing = False

    def redo(self):
        self._undoing = True # We need to prevent the changes made in redo() from being added to the undo stack
        self.model.undo_manager.redo()
        self._undoing = False

    def apply_message_model(self, message_model_serial: str):
        logger.debug(f"Display state triggered with model: {message_model_serial}")

        message_model = DeviceViewerMessageModel.deserialize(message_model_serial)

        if message_model.uuid == self.model.uuid:
            return  # Ignore messages that are from the same model

        # Reset the model to clear any existing routes and channels
        self._disable_state_messages = True  # Prevent state messages from being sent while we apply the new state
        self._undoing = True  # Prevent changes from being added to the undo stack (otherwise model changes are undone during playback)
        self.model.reset()

        # Apply step ID
        self.model.step_id = message_model.step_id

        # Apply step label
        self.model.step_label = message_model.step_label

        # Apply free mode
        self.model.free_mode = message_model.free_mode

        # Apply editable state
        self.model.editable = message_model.editable

        # Apply electrode channel mapping
        for electrode_id, electrode in self.model.electrodes.electrodes.items():
            electrode.channel = message_model.id_to_channel.get(electrode_id, electrode.channel)

        # Apply electrode on/off states
        self.model.electrodes.channels_states_map.update(message_model.channels_activated)

        # Apply routes
        for route, color in message_model.routes:
            self.model.routes.add_layer(Route(route=route.copy()), None, color)
        self.model.routes.selected_layer = None

        self._disable_state_messages = False  # Re-enable state messages after reset
        self._undoing = False
        self.undo_manager.active_stack.clear()  # Clear the undo stack

    def publish_model_message(self):
        logger.debug(f"Publishing message for updated viewer state {self.message_buffer}")
        publish_message(topic=DEVICE_VIEWER_STATE_CHANGED, message=self.message_buffer)

    def publish_electrode_update(self):
        message_obj = {}
        for channel in self.model.electrodes.channels_electrode_ids_map: # Make sure all channels are explicitly included
            message_obj[channel] = self.model.electrodes.channels_states_map.get(channel, False)
        publish_message(topic=ELECTRODES_STATE_CHANGE, message=json.dumps(message_obj))

    def publish_detect_droplet(self):
        publish_message(topic=DETECT_DROPLETS, message=json.dumps(list(self.model.electrodes.channels_electrode_ids_map.keys())))

    def publish_calibration_message(self):
        """
        Publish a message with the current calibration values.
        """
        message = {
            "liquid_capacitance_over_area": self.model.liquid_capacitance_over_area, # In pF/mm^2
            "filler_capacitance_over_area": self.model.filler_capacitance_over_area, # In pF/mm^2
        }
        logger.warning(f"Publishing calibration message: {message}")
        publish_message(topic=CALIBRATION_DATA, message=json.dumps(message))
        logger.info(f"Published calibration message: {message}")

    def create_contents(self, parent):
        """Called when the task is activated."""
        logger.debug(f"Device Viewer Task activated. Setting default view with {self.device_viewer_preferences.DEFAULT_SVG_FILE}...")
        self.set_interaction_service(self.model)

        # Initialize camera primitives
        self.capture_session = QMediaCaptureSession()  # Initialize capture session for the device viewer
        self.video_item = QGraphicsVideoItem()
        self.video_item.setZValue(-100)  # Set a low z-value to ensure the video is behind other items
        self.opencv_pixmap = QGraphicsPixmapItem()
        self.opencv_pixmap.setZValue(-100)  # Set a low z-value to ensure the pixmap is behind other items
        self.opencv_pixmap.setVisible(False)  # Initially hide the pixmap item

        scene_rect = self.device_view.viewport().rect()  # Get the viewport rectangle of the device view
        self.video_item.setSize(QSizeF(scene_rect.width(), scene_rect.height()))  # Set the size of the video item
        self.capture_session.setVideoOutput(self.video_item)
        self.scene.addItem(self.video_item)
        self.scene.addItem(self.opencv_pixmap)  # Add the pixmap item to the scene

        # Create debounce timer
        self.debounce_timer = QTimer()
        self.debounce_timer.setSingleShot(True)
        self.debounce_timer.timeout.connect(self.publish_model_message)

        # Layout init for device view and its property editor right-side bar
        # left side will house device viewer; right side a collapsible scrollable stack of collapsible widgets
        main_layout = QHBoxLayout()
        main_container = QWidget()

        # --- Right Side: Collapsible Scroll Area ---

        # Create the Scroll Area and its container
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)

        scroll_area.setMaximumWidth(self.device_viewer_preferences.DEVICE_VIEWER_SIDEBAR_WIDTH)
        # Initially hide the scroll area
        scroll_area.setVisible(True)

        scroll_content = QWidget()
        scroll_content.setMaximumWidth(self.device_viewer_preferences.DEVICE_VIEWER_SIDEBAR_WIDTH-5) # offset to fit within the area
        scroll_layout = QVBoxLayout(scroll_content)

        # device_view code
        self.device_view.display_state_signal.connect(self.apply_message_model)

        #### Side Bar widgets init #####

        # alpha_view code
        self.alpha_view_ui = self.model.edit_traits(view=alpha_table_view)

        self.alpha_view_ui.control.setMinimumHeight(self.device_viewer_preferences.ALPHA_VIEW_MIN_HEIGHT)
        self.alpha_view_ui.control.setMaximumWidth(self.device_viewer_preferences.DEVICE_VIEWER_SIDEBAR_WIDTH)
        self.alpha_view_ui.control.setParent(main_container)

        # layer_view code
        layer_view = RouteLayerView
        self.layer_ui = self.model.routes.edit_traits(view=layer_view)

        self.layer_ui.control.setMinimumHeight(self.device_viewer_preferences.LAYERS_VIEW_MIN_HEIGHT)
        self.layer_ui.control.setParent(main_container)

        # mode_picker_view code
        self.mode_picker_view = ModePicker(self.model, self)
        self.mode_picker_view.setParent(main_container)

        # camera_control_widget code
        self.camera_control_widget = CameraControlWidget(self.model, self.capture_session, self.video_item, self.opencv_pixmap, self.scene, self.app_preferences)
        self.camera_control_widget.setParent(main_container)

        # calibration_view code
        self.calibration_view = CalibrationView(self.model)
        self.calibration_view.setParent(main_container)

        scroll_layout.addWidget(
            CollapsibleVStackBox("Camera Controls", control_widgets=[self.camera_control_widget, self.alpha_view_ui.control])
        )
        scroll_layout.addWidget(
            CollapsibleVStackBox("Paths", control_widgets=[self.layer_ui.control, self.mode_picker_view])
        )
        scroll_layout.addWidget(
            CollapsibleVStackBox("Calibration", control_widgets=self.calibration_view)
        )
        scroll_layout.addStretch()

        scroll_area.setWidget(scroll_content)

        reveal_button = QPushButton("chevron_right")

        # Create a button to show/hide the scroll area

        def reveal_button_handler():
            # 1. Check the current visibility of the scroll_area
            is_now_visible = not scroll_area.isVisible()

            # 2. Toggle the visibility of the entire scroll_area
            scroll_area.setVisible(is_now_visible)

            # 3. Update the button icon based on the new state
            #    (chevron_right to hide, chevron_left to reveal)
            reveal_button.setText("chevron_right" if is_now_visible else "chevron_left")

        # Import and apply centralized button styles with proper tooltip styling
        try:
            theme = "dark" if is_dark_mode() else "light"
            narrow_style = get_complete_stylesheet(theme, "narrow")
            reveal_button.setStyleSheet(narrow_style)
        except ImportError:
            # Fallback to custom styling if centralized styles aren't available
            reveal_button.setStyleSheet("font-family: Material Symbols Outlined; font-size: 30px; margin-left: 3px; margin-right: 3px; padding-left: 3px;")

        reveal_button.setToolTip("Reveal Hidden Controls")
        reveal_button.clicked.connect(reveal_button_handler)
        reveal_button.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Expanding)

        ####### Assemble main layout ################
        main_layout.addWidget(self.device_view, 1) # left side
        main_layout.addWidget(reveal_button) # middle
        main_layout.addWidget(scroll_area) # right side

        main_container.setLayout(main_layout)


        # Apply initial theme styling
        self._apply_initial_theme_styling()

        return main_container

    def set_view_from_model(self, new_electrodes_model: 'Electrodes'):
        self.remove_current_layer()
        self.current_electrode_layer = ElectrodeLayer(new_electrodes_model)
        self.current_electrode_layer.add_all_items_to_scene(self.scene)
        self.scene.setSceneRect(self.scene.itemsBoundingRect())
        self.device_view.fitInView(self.scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self.undo_manager.active_stack.clear()

    def _on_load_svg_success(self):
        """Open a file dialog to select an SVG file and set it in the central pane."""
        svg_file = self.device_viewer_preferences.DEFAULT_SVG_FILE # since OK, the default should have changed now.
        logger.info(f"Selected SVG file: {svg_file}")

        self.model.reset()
        self.current_electrode_layer.set_loading_label()  # Set loading label while the SVG is being processed
        self.model.electrodes.set_electrodes_from_svg_file(svg_file) # Slow! Calculating centers via np.mean
        logger.debug(f"Created electrodes from SVG file: {self.model.electrodes.svg_model.filename}")

        self.set_interaction_service(self.model)
        logger.info(f"Electrodes model set to {self.model}")

    def load_svg_dialog(self):
        logger.info("\n--- Loading external svg file into device repo ---")

        # --- 1. Open a dialog for the user to select a source file ---
        # This is decoupled from self.file to allow loading any file at any time.
        dialog = FileDialog(action='open',
                            default_path=str(self.device_viewer_preferences.DEFAULT_SVG_FILE),
                            wildcard='SVG Files (*.svg)|*.svg|All Files (*.*)|*.*')

        if dialog.open() != OK:
            logger.info("File selection cancelled by user.")
            return None

        src_file = Path(dialog.path)
        repo_dir = Path(self.device_viewer_preferences.DEVICE_REPO_DIR)

        # --- 3. Handle case where the selected file is already in the repo ---
        # We just select it in the UI and do not need to copy anything.
        if src_file.parent == repo_dir:
            logger.debug(f"File '{src_file.name}' is already in the repo. Selecting it.")
            self.device_viewer_preferences.DEFAULT_SVG_FILE = src_file
            self._on_load_svg_success()
            return OK

        logger.debug("Checking for chosen file in repo...")
        dst_file = Path(repo_dir) / src_file.name

        if not dst_file.exists():
            # --- 4a. No conflict: The file doesn't exist, copy it directly.

            self.device_viewer_preferences.DEFAULT_SVG_FILE = safe_copy_file(src_file, dst_file)

            logger.info(f"{dst_file.name} has been copied to {src_file.name}. It was not found in the repo before.")

            self._on_load_svg_success()
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
                self.device_viewer_preferences.DEFAULT_SVG_FILE = safe_copy_file(src_file, dst_file)

                self._on_load_svg_success()
                return OK

            elif confirm_overwrite == NO:
                # --- Open a 'Save As' dialog to choose a new name ---
                logger.debug("User chose 'Save As...'. Opening save dialog.")

                dialog = FileDialog(action='save as',
                                    default_directory=str(repo_dir),
                                    default_filename=src_file.stem + " - Copy",
                                    wildcard='Texts (*.txt)')

                ###### Handle Save As Dialog ######################
                if dialog.open() == OK:
                    dst_file = dialog.path

                    self.device_viewer_preferences.DEFAULT_SVG_FILE = safe_copy_file(src_file, dst_file)

                    self._on_load_svg_success()
                    return OK

                else:
                    logger.debug("Save As dialog cancelled by user.")
                    return None

                ####################################################

            else:  # result == CANCEL
                logger.debug("Load operation cancelled by user.")
                return None


    def save_svg_dialog(self):
        """Open a file dialog to save the current model to an SVG file."""
        dialog = FileDialog(action='save as', wildcard='SVG Files (*.svg)|*.svg')
        if dialog.open() == OK:
            new_filename = dialog.path if dialog.path.endswith(".svg") else str(dialog.path) + ".svg"
            channels_to_svg(self.model.electrodes.svg_model.filename, new_filename,
                            self.model.electrodes.electrode_ids_channels_map, self.model.electrode_scale)

    @observe("model.camera_perspective.transformation")
    @observe("model.camera_perspective.camera_resolution")
    def camera_perspective_change_handler(self, event):
        """
        Handle changes to the camera perspective transformation.
        This is used to update the scene's transformation when the camera perspective changes.
        """
        if not self.model.camera_perspective.camera_resolution:
            return
        
        if self.video_item:
            self.video_item.setTransform(self.model.camera_perspective.transformation)
        if self.opencv_pixmap:
            scale = QTransform()
            scale.scale(self.scene.width() / self.model.camera_perspective.camera_resolution[0],
                        self.scene.height() / self.model.camera_perspective.camera_resolution[1])
            self.opencv_pixmap.setTransform(scale * self.model.camera_perspective.transformation)

    @observe("model.alpha_map.items.[alpha, visible]")
    def _alpha_change(self, event):
        if self.video_item:
            self.video_item.setOpacity(self.model.get_alpha("video"))
        if self.opencv_pixmap:
            self.opencv_pixmap.setOpacity(self.model.get_alpha("opencv_pixmap"))

def create_line():
    line = QFrame()
    line.setStyleSheet("padding: 0px; margin: 0px;")
    line.setFrameShape(QFrame.HLine)
    line.setFrameShadow(QFrame.Sunken)
    return line