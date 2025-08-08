import sys
import copy
import json
from PySide6.QtWidgets import (QTreeView, QVBoxLayout, QWidget, QHBoxLayout,
                               QFileDialog, QMessageBox, QApplication, QMainWindow, 
                               QPushButton, QDialog)
from PySide6.QtCore import Qt, QItemSelectionModel, QTimer, Signal, QEvent
from PySide6.QtGui import QStandardItemModel, QKeySequence, QShortcut, QBrush, QColor

from microdrop_application.application import is_dark_mode
from protocol_grid.protocol_grid_helpers import (PGCItem, make_row, ProtocolGridDelegate, 
                                               calculate_group_aggregation_from_children)
from protocol_grid.state.protocol_state import ProtocolState, ProtocolStep, ProtocolGroup
from protocol_grid.protocol_state_helpers import flatten_protocol_for_run
from protocol_grid.consts import (DEVICE_VIEWER_STATE_CHANGED, PROTOCOL_GRID_DISPLAY_STATE, 
                                  GROUP_TYPE, STEP_TYPE, ROW_TYPE_ROLE, step_defaults, 
                                  group_defaults, protocol_grid_fields, protocol_grid_column_widths)
from protocol_grid.extra_ui_elements import (EditContextMenu, ColumnToggleDialog,
                                             NavigationBar, StatusBar, make_separator,
                                             InformationPanel, ExperimentCompleteDialog,
                                             DropbotDisconnectedBeforeRunDialogAction)
from protocol_grid.services.device_viewer_listener_controller import DeviceViewerListenerController
from protocol_grid.services.protocol_runner_controller import ProtocolRunnerController
from protocol_grid.services.experiment_manager import ExperimentManager
from protocol_grid.services.protocol_state_tracker import ProtocolStateTracker
from protocol_grid.services.voltage_frequency_service import VoltageFrequencyService
from device_viewer.models.messages import DeviceViewerMessageModel
from protocol_grid.state.device_state import (DeviceState, device_state_from_device_viewer_message,
                                              device_state_to_device_viewer_message)
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message
from microdrop_style.icons.icons import ICON_PLAY, ICON_PAUSE, ICON_RESUME
from microdrop_utils._logger import get_logger

logger = get_logger(__name__)


class PGCWidget(QWidget):
    
    protocolChanged = Signal()
    
    def __init__(self, parent=None, state=None):
        super().__init__(parent)

        self._setup_listener()

        self.state = state or ProtocolState()

        self.protocol_runner = ProtocolRunnerController(self.state, flatten_protocol_for_run)
        self.protocol_runner.signals.highlight_step.connect(self.highlight_step)
        self.protocol_runner.signals.update_status.connect(self.update_status_bar)
        self.protocol_runner.signals.protocol_finished.connect(self.on_protocol_finished)
        self.protocol_runner.signals.protocol_paused.connect(self.on_protocol_paused)    
        self.protocol_runner.signals.protocol_error.connect(self.on_protocol_error) 
        self.protocol_runner.signals.select_step.connect(self.select_step_by_uid)

        self.experiment_manager = ExperimentManager()
        self.experiment_manager.initialize()  

        self.protocol_state_tracker = ProtocolStateTracker()        
        
        self._column_visibility = {}
        self._column_widths = {}
        
        self.tree = QTreeView()
        self.model = QStandardItemModel()
        self.tree.setModel(self.model)
        self.delegate = ProtocolGridDelegate(self)
        self.tree.setItemDelegate(self.delegate)
        
        self.tree.setSelectionBehavior(QTreeView.SelectRows)
        self.tree.setSelectionMode(QTreeView.ExtendedSelection)

        self._protocol_running = False 
        self._processing_palette_change = False
        self._last_published_step_id = None
        self._last_selected_step_id = None
        self._last_published_step_uid = None
        self._processing_device_viewer_message = False
        self._navigating = False

        # debounce setup for Qt thread
        self._play_pause_debounce_timer = QTimer()
        self._play_pause_debounce_timer.setSingleShot(True)
        self._play_pause_debounce_timer.timeout.connect(self._execute_debounced_play_pause)
        self._pending_play_pause_action = None
        self._debounce_delay_ms = 250
        
        self.create_buttons()

        self.information_panel = InformationPanel(self)
        self.information_panel.open_button.clicked.connect(self.open_experiment_directory)        
        self.information_panel.update_experiment_id(self.experiment_manager.get_experiment_id())
        self.information_panel.update_protocol_name(self.protocol_state_tracker.get_protocol_display_name())
        
        self.navigation_bar = NavigationBar(self)
        self.navigation_bar.btn_play.clicked.connect(self.toggle_play_pause)
        self.navigation_bar.btn_stop.clicked.connect(self.stop_protocol)
        self.navigation_bar.btn_first.clicked.connect(self.navigate_to_first_step)
        self.navigation_bar.btn_prev.clicked.connect(self.navigate_to_previous_step)
        self.navigation_bar.btn_next.clicked.connect(self.navigate_to_next_step)
        self.navigation_bar.btn_last.clicked.connect(self.navigate_to_last_step) 
        self.navigation_bar.btn_prev_phase.clicked.connect(self.navigate_previous_phase)
        self.navigation_bar.btn_resume.clicked.connect(self.toggle_play_pause)
        self.navigation_bar.btn_next_phase.clicked.connect(self.navigate_next_phase)

        self.status_bar = StatusBar(self)

        layout = QVBoxLayout()
        layout.addWidget(self.information_panel)
        layout.addWidget(make_separator())
        layout.addWidget(self.navigation_bar)
        layout.addWidget(make_separator())
        layout.addWidget(self.status_bar)
        layout.addWidget(make_separator())
        layout.addWidget(self.tree)
        layout.addLayout(self.button_layout_1)  # Add/Insert buttons
        layout.addLayout(self.button_layout_2)  # Import/Export buttons
        self.setLayout(layout)
        
        self._programmatic_change = False
        self._block_aggregation = False
        self._sync_timer = QTimer()
        self._sync_timer.setSingleShot(True)
        self._sync_timer.timeout.connect(self._delayed_sync)
        self._clipboard = []
        
        self.model.itemChanged.connect(self.on_item_changed)
        self.tree.selectionModel().selectionChanged.connect(self.on_selection_changed)
        
        self.setup_context_menu()
        self.setup_shortcuts()
        self.setup_header_context_menu()        
        self.ensure_minimum_protocol()
        self.load_from_state()
        self._update_navigation_buttons_state()
        self._update_ui_enabled_state()

        self._protocol_grid_plugin = None

    # ---------- DropBot connection ----------
    def _is_dropbot_connected(self):
        if self._protocol_grid_plugin and hasattr(self._protocol_grid_plugin, 'dropbot_connected'):
            return self._protocol_grid_plugin.dropbot_connected
        
        # fallback
        logger.info("Cannot determine dropbot connection status, assuming disconnected")
        return False

    def _check_dropbot_connection_and_show_dialog(self):
        preview_mode = self.navigation_bar.is_preview_mode()
        
        if preview_mode:
            return True
        
        if self._is_dropbot_connected():
            return True
        
        dialog_action = DropbotDisconnectedBeforeRunDialogAction()
        
        def show_dialog_safe():
            try:
                preview_mode_requested = dialog_action.perform(self)
                if preview_mode_requested:
                    self.navigation_bar.preview_mode_checkbox.setChecked(True)
                    logger.info("Preview mode enabled by user request from dropbot disconnection dialog")
                return False
            except Exception as e:
                logger.info(f"Error showing dropbot disconnection dialog: {e}")
                return False
        
        # for immediate protocol execution requests, block and show dialog
        try:
            preview_mode_requested = dialog_action.perform(self)
            if preview_mode_requested:
                self.navigation_bar.preview_mode_checkbox.setChecked(True)
                logger.info("Preview mode enabled by user request from dropbot disconnection dialog")
            return False
        except Exception as e:
            logger.info(f"Error showing dropbot disconnection dialog: {e}")
            return False
    #-----------------------------------------


    # ---------- Message Handling ----------    
    def _setup_listener(self):
        try:
            app_instance = None
            
            qt_app = QApplication.instance()
            if qt_app:
                for widget in qt_app.allWidgets():
                    if hasattr(widget, 'application') and widget.application:
                        app_instance = widget.application
                        break
            
            # find the protocol grid plugin and get its listener
            if app_instance and hasattr(app_instance, 'plugin_manager'):
                for plugin in app_instance.plugin_manager._plugins:
                    if hasattr(plugin, 'id') and plugin.id == "protocol_grid.plugin":
                        self._protocol_grid_plugin = plugin
                        listener = plugin.get_listener()
                        if listener:
                            # connect to device viewer messages
                            listener.signal_emitter.device_viewer_message_received.connect(
                                self.on_device_viewer_message
                            )
                            logger.info("Connected to message listener")
                            return
                        break

            logger.info("Could not connect to message listener")

        except Exception as e:
            logger.info(f"Error setting up message listener: {e}")

    def on_device_viewer_message(self, message, topic):
        if topic != DEVICE_VIEWER_STATE_CHANGED:
            return        
        if self._protocol_running:
            return
        self._processing_device_viewer_message = True
        self._programmatic_change = True

        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        try:
            dv_msg = DeviceViewerMessageModel.deserialize(message)            
            if not dv_msg.step_id:
                return
                
            target_item, target_path = self._find_step_by_uid(dv_msg.step_id)
            if not target_item:
                return  # no step found with matching UID
            
            current_step_id = self._last_selected_step_id
            current_published_id = self._last_published_step_id
            
            # get current device state to check id_to_channel
            current_device_state = target_item.data(Qt.UserRole + 100)
            current_id_to_channel = current_device_state.id_to_channel if current_device_state else {}
            
            device_state = device_state_from_device_viewer_message(dv_msg)
            
            # check if id_to_channel mapping has changed
            if device_state.id_to_channel != current_id_to_channel:
                self._apply_id_to_channel_mapping_to_all_steps(device_state.id_to_channel, device_state.route_colors)
            else:
                target_item.setData(device_state, Qt.UserRole + 100)
            
            self.model_to_state()
            
            # Restore the selection state to prevent false "deselection" detection
            self._last_selected_step_id = current_step_id
            self._last_published_step_id = current_published_id
            
            # Restore scroll and selection BEFORE clearing blocking flags
            self.restore_scroll_positions(scroll_pos)
            self.restore_selection(saved_selection)
        
        except Exception as e:
            logger.info(f"Failed to update DeviceState from device_viewer message: {e}")
        finally:
            self._processing_device_viewer_message = False
            self._programmatic_change = False        
    # -------------------------------------

    # ---------- Information Panel Methods ----------
    def open_experiment_directory(self):
        """open experiment directory in file explorer."""
        self.experiment_manager.open_experiment_directory()

    def _update_protocol_display(self):
        display_name = self.protocol_state_tracker.get_protocol_display_name()
        self.information_panel.update_protocol_name(display_name)

    def _mark_protocol_modified(self):
        """mark the protocol as modified and update display."""
        if not self.protocol_state_tracker.is_modified():
            self.protocol_state_tracker.mark_modified(True)
            self._update_protocol_display()
    # -----------------------------------------------

    # ---------- Protocol Navigation Bar / Status Bar / Runner Methods ----------
    def is_protocol_running(self):
            return self._protocol_running

    def highlight_step(self, path):
        self.clear_highlight()
        item = self.get_item_by_path(path)
        if item:
            parent = item.parent() or self.model.invisibleRootItem()
            row = item.row()
            for col in range(self.model.columnCount()):
                cell = parent.child(row, col)
                if cell:
                    cell.setBackground(Qt.blue)
                    cell.setForeground(Qt.white)

            if self._protocol_running:
                self._scroll_to_highlighted_step(path)

    def _scroll_to_highlighted_step(self, path):
        if not path:
            return
        
        # model index for the first column of the highlighted row
        index = self.model.index(path[0], 0)
        for row in path[1:]:
            if index.isValid():
                index = self.model.index(row, 0, index)
            else:
                return
        
        if index.isValid():
            # scroll to the item, leave some padding
            self.tree.scrollTo(index, QTreeView.PositionAtCenter)
            
            # expand if group
            item = self.get_item_by_path(path)
            if item and item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                parent_index = index.parent()
                while parent_index.isValid():
                    self.tree.expand(parent_index)
                    parent_index = parent_index.parent()
            
            self.tree.expand(index)

    def clear_highlight(self):
        if getattr(self, '_processing_palette_change', False):
            return
            
        dark = is_dark_mode()
        fg = QBrush(QColor("white" if dark else "black"))
        def clear_recursive(parent):
            for row in range(parent.rowCount()):
                for col in range(parent.columnCount()):
                    item = parent.child(row, col)
                    if item:
                        item.setBackground(QBrush())
                        item.setForeground(fg)
                desc_item = parent.child(row, 0)
                if desc_item and desc_item.hasChildren():
                    clear_recursive(desc_item)
        clear_recursive(self.model.invisibleRootItem())

    def update_status_bar(self, status):
        self.status_bar.lbl_total_time.setText(f"Total Time: {status['total_time']:.2f} s")
        self.status_bar.lbl_step_time.setText(f"Step Time: {status['step_time']:.2f} s")
        self.status_bar.lbl_step_progress.setText(f"Step {status['step_idx']}/{status['step_total']}")
        self.status_bar.lbl_step_repetition.setText(f"Repetition {status['step_rep_idx']}/{status['step_rep_total']}")
        self.status_bar.lbl_recent_step.setText(f"Most Recent Step: {status['recent_step']}")
        self.status_bar.lbl_next_step.setText(f"Next Step: {status['next_step']}")
        if "protocol_repeat_idx" in status and "protocol_repeat_total" in status:
            self.status_bar.lbl_repeat_protocol_status.setText(f"{status['protocol_repeat_idx']}/")
        else:
            self.status_bar.lbl_repeat_protocol_status.setText("1/")

    def on_protocol_finished(self):
        self.clear_highlight()
        self._protocol_running = False
        self._disable_phase_navigation()

        self.navigation_bar.btn_play.setText(ICON_PLAY)
        self.navigation_bar.btn_play.setToolTip("Play Protocol")

        self._update_navigation_buttons_state()
        self._update_ui_enabled_state() 

        # handle auto-save and new experiment creation based on mode
        advanced_mode = self.navigation_bar.is_advanced_user_mode()
        
        if advanced_mode:
            # advanced mode: show dialog and handle response
            self._handle_advanced_mode_completion()
        else:
            # regular mode: auto-save and create new experiment
            self._handle_regular_mode_completion()
        
        QTimer.singleShot(10, self._cleanup_after_protocol_operation)

    def _handle_regular_mode_completion(self):
        """handle protocol completion in regular mode: auto-save + new experiment."""
        try:
            # auto-save current protocol with smart filename
            protocol_data = self.state.to_flat_export()
            protocol_name = self.protocol_state_tracker.get_protocol_name()
            is_modified = self.protocol_state_tracker.is_modified()
            
            saved_path = self.experiment_manager.auto_save_protocol(
                protocol_data, protocol_name, is_modified
            )
            
            if saved_path:
                # update protocol state tracker to reflect the auto-saved protocol
                self.protocol_state_tracker.set_saved_protocol(saved_path)
                self._update_protocol_display()
                logger.info(f"Protocol auto-saved to: {saved_path}")
            
            # initialize new experiment
            new_experiment_id = self.experiment_manager.initialize_new_experiment()
            if new_experiment_id:
                # update information panel with new experiment ID
                self.information_panel.update_experiment_id(new_experiment_id)
                logger.info(f"Started new experiment: {new_experiment_id}")
            
        except Exception as e:
            logger.error(f"Error handling regular mode completion: {e}")

    def _handle_advanced_mode_completion(self):
        """handle protocol completion in advanced mode: show dialog."""       
        try:
            dialog = ExperimentCompleteDialog(self)
            result = dialog.exec()
            
            if result == QDialog.Accepted:
                # user chose YES: same as regular mode
                self._handle_regular_mode_completion()
            # if NO or closed: do nothing, stay with current experiment
            
        except Exception as e:
            logger.error(f"Error handling advanced mode completion: {e}")

    def _cleanup_after_protocol_operation(self):
        if not getattr(self, '_programmatic_change', False):
            self._programmatic_change = True
            try:
                self._clean_group_parameters_recursive(self.state.sequence)
                
                self.load_from_state()
            finally:
                self._programmatic_change = False

    def _clean_group_parameters_recursive(self, elements):
        allowed_group_fields = {
            "Description", "ID", "Repetitions", "Duration", "Run Time",
            "Voltage", "Frequency", "Trail Length", "UID"
        }
        
        for element in elements:
            if hasattr(element, "elements"): # group 
                filtered_parameters = {}
                for field, value in element.parameters.items():
                    if field in allowed_group_fields:
                        filtered_parameters[field] = value
                element.parameters = filtered_parameters
                
                self._clean_group_parameters_recursive(element.elements)

    def on_protocol_paused(self):
        self.navigation_bar.btn_play.setText(ICON_RESUME)
        self.navigation_bar.btn_play.setToolTip("Resume Protocol")

        if self.protocol_runner.can_navigate_phases():
            self._enable_phase_navigation()
        else:
            self._disable_phase_navigation()
    
    def on_protocol_error(self, error_message):
        logger.info(f"Protocol execution error: {error_message}")
        self.clear_highlight()
        self.reset_status_bar()
        self._protocol_running = False

        self.navigation_bar.btn_play.setText(ICON_PLAY)
        self.navigation_bar.btn_play.setToolTip("Play Protocol")

        self._update_navigation_buttons_state()
        self._update_ui_enabled_state()

        # clear selection on error
        self.tree.clearSelection()
        self._last_selected_step_id = None
        self._last_published_step_id = None

    def select_step_by_uid(self, step_uid):
        """select step by when protocol finishes/stops."""
        if not step_uid:
            return
        
        step_item, step_path = self._find_step_by_uid(step_uid)
        
        if step_item and step_path:
            self.tree.clearSelection()
            
            self._select_step_by_path(step_path)
            
            # manually update internal tracking
            parent = step_item.parent() or self.model.invisibleRootItem()
            row = step_item.row()
            id_col = protocol_grid_fields.index("ID")
            id_item = parent.child(row, id_col)
            step_id = id_item.text() if id_item else ""
            
            self._last_selected_step_id = step_id
            # didnt update _last_published_step_id here since we want the message to be published

    def navigate_to_first_step(self):
        self._navigating = True
        all_step_paths = self._get_all_step_paths()
        if not all_step_paths:
            return
        
        target_path = all_step_paths[0]
        
        if self._protocol_running and self.navigation_bar.is_advanced_user_mode():
            self._navigate_during_protocol(target_path)
        elif not self._protocol_running:
            self._select_step_by_path(target_path)
        self._navigating = False

    def navigate_to_previous_step(self):
        self._navigating = True
        all_step_paths = self._get_all_step_paths()
        if not all_step_paths:
            return
        
        if self._protocol_running and self.navigation_bar.is_advanced_user_mode():
            current_path = self.protocol_runner.get_current_step_path()
            if current_path:
                try:
                    current_index = all_step_paths.index(current_path)
                    if current_index > 0:
                        target_path = all_step_paths[current_index - 1]
                        self._navigate_during_protocol(target_path)
                except ValueError:
                    pass
        elif not self._protocol_running:
            current_index = self._get_current_step_index()
            if current_index == -1:
                if all_step_paths:
                    self._select_step_by_path(all_step_paths[-1])
            elif current_index > 0:
                self._select_step_by_path(all_step_paths[current_index - 1])
        self._navigating = False

    def navigate_to_next_step(self):
        self._navigating = True
        all_step_paths = self._get_all_step_paths()
        if not all_step_paths:
            return
        
        if self._protocol_running and self.navigation_bar.is_advanced_user_mode():
            current_path = self.protocol_runner.get_current_step_path()
            if current_path:
                try:
                    current_index = all_step_paths.index(current_path)
                    if current_index + 1 < len(all_step_paths):
                        target_path = all_step_paths[current_index + 1]
                        self._navigate_during_protocol(target_path)
                except ValueError:
                    pass
        elif not self._protocol_running:
            current_index = self._get_current_step_index()
            if current_index == -1:
                if all_step_paths:
                    self._select_step_by_path(all_step_paths[0])
            elif current_index + 1 < len(all_step_paths):
                self._select_step_by_path(all_step_paths[current_index + 1])
            else:
                self._add_step_at_root_and_select()
        self._navigating = False

    def navigate_to_last_step(self):
        self._navigating = True
        all_step_paths = self._get_all_step_paths()
        if not all_step_paths:
            return
        
        target_path = all_step_paths[-1]
        
        if self._protocol_running and self.navigation_bar.is_advanced_user_mode():
            self._navigate_during_protocol(target_path)
        elif not self._protocol_running:
            self._select_step_by_path(target_path)
        self._navigating = False

    def _qt_debounce_play_pause(self, action_func):
        # store the action to execute
        self._pending_play_pause_action = action_func
        
        # reset the timer - cancel any pending execution
        self._play_pause_debounce_timer.stop()
        self._play_pause_debounce_timer.start(self._debounce_delay_ms)

    def _execute_debounced_play_pause(self):
        if self._pending_play_pause_action:
            try:
                self._pending_play_pause_action()
            except Exception as e:
                logger.error(f"Error in debounced play/pause action: {e}")
            finally:
                self._pending_play_pause_action = None

    def _play_pause_start_protocol(self):
        self._protocol_running = True
        self.sync_to_state()
        try:
            repeat_n = int(self.status_bar.edit_repeat_protocol.text() or "1")
        except ValueError:
            repeat_n = 1

        selected_paths = self.get_selected_paths()
        start_step_path = None
        if selected_paths:
            first_selected_item = self.get_item_by_path(selected_paths[0])
            if first_selected_item and first_selected_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                start_step_path = selected_paths[0]

        if not start_step_path:
            all_step_paths = self._get_all_step_paths()
            start_step_path = all_step_paths[0] if all_step_paths else None

        flat_run = flatten_protocol_for_run(self.state)

        start_idx = 0
        for idx, entry in enumerate(flat_run):
            if entry["path"] == start_step_path:
                start_idx = idx
                break

        # Repeat Protocol 
        run_order = []
        for repeat_idx in range(repeat_n):
            run_order.extend(flat_run[start_idx:])

        preview_mode = self.navigation_bar.is_preview_mode()
        advanced_mode = self.navigation_bar.is_advanced_user_mode()
        
        self.protocol_runner.set_preview_mode(preview_mode)
        self.protocol_runner.set_repeat_protocol_n(repeat_n)
        self.protocol_runner.set_run_order(run_order)        
        self.protocol_runner.set_advanced_hardware_mode(advanced_mode, preview_mode)
        
        self.protocol_runner.start()

        self.navigation_bar.btn_play.setText(ICON_PAUSE)
        self.navigation_bar.btn_play.setToolTip("Pause Protocol")

        self._update_navigation_buttons_state()
        self._update_ui_enabled_state()
        
        # clear selection when protocol starts
        self.tree.clearSelection()
        self._last_selected_step_id = None
        self._last_published_step_id = None

    def _play_pause_pause_protocol(self):
        advanced_mode = self.navigation_bar.is_advanced_user_mode()
        preview_mode = self.navigation_bar.is_preview_mode()
        self.protocol_runner.pause(advanced_mode=advanced_mode, preview_mode=preview_mode)

        self.navigation_bar.btn_play.setText(ICON_RESUME)
        self.navigation_bar.btn_play.setToolTip("Resume Protocol")

        self._update_navigation_buttons_state()

    def _play_pause_resume_protocol(self):
        # self.sync_to_state()
        advanced_mode = self.navigation_bar.is_advanced_user_mode()
        preview_mode = self.navigation_bar.is_preview_mode()
        
        self._disable_phase_navigation()
        
        self.protocol_runner.resume(advanced_mode=advanced_mode, preview_mode=preview_mode)
        self._protocol_running = True

        self.navigation_bar.btn_play.setText(ICON_PAUSE)
        self.navigation_bar.btn_play.setToolTip("Pause Protocol")

        self._update_navigation_buttons_state()
        
        # Clear selection when resuming to ensure runtime highlight is visible
        self.tree.clearSelection()
        self._last_selected_step_id = None
        self._last_published_step_id = None

    def toggle_play_pause(self):
        # check dropbot connection before any protocol operation
        if not self.protocol_runner.is_running() and not self.protocol_runner.is_paused():
            if not self._check_dropbot_connection_and_show_dialog():
                return
            
        if self.protocol_runner.is_running():
            self.navigation_bar.btn_play.setText(ICON_RESUME)
            self.navigation_bar.btn_play.setToolTip("Resume Protocol")

            self._qt_debounce_play_pause(self._play_pause_pause_protocol)
            
        elif self.protocol_runner.is_paused():
            self.navigation_bar.btn_play.setText(ICON_PAUSE)
            self.navigation_bar.btn_play.setToolTip("Pause Protocol")

            self._qt_debounce_play_pause(self._play_pause_resume_protocol)
            
        else:
            self.navigation_bar.btn_play.setText(ICON_PAUSE)
            self.navigation_bar.btn_play.setToolTip("Pause Protocol")

            self._qt_debounce_play_pause(self._play_pause_start_protocol)

    def run_selected_step(self):
        if self._protocol_running:
            return

        if not self._check_dropbot_connection_and_show_dialog():
            return
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
        
        # find first selected step if multiple steps are selected
        target_step_path = None
        for path in selected_paths:
            item = self.get_item_by_path(path)
            if item and item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                target_step_path = path
                break
        
        if not target_step_path:
            return
        
        self._protocol_running = True
        self.sync_to_state()
        
        target_step_item = self.get_item_by_path(target_step_path)
        if not target_step_item:
            return
        
        parent = target_step_item.parent() or self.model.invisibleRootItem()
        row = target_step_item.row()
        
        parameters = {}
        for col, field in enumerate(protocol_grid_fields):
            item = parent.child(row, col)
            if item:
                if field == "Magnet":
                    parameters[field] = "1" if self._is_checkbox_checked(item) else "0"
                else:
                    parameters[field] = item.text()
        
        # temporary step object
        from protocol_grid.state.protocol_state import ProtocolStep
        temp_step = ProtocolStep(parameters=parameters, name=parameters.get("Description", "Step"))
        
        device_state = target_step_item.data(Qt.UserRole + 100)
        if device_state:
            temp_step.device_state = device_state
        else:
            temp_step.device_state = DeviceState()
        
        run_order = [{
            "step": temp_step,
            "path": target_step_path,
            "rep_idx": 1,
            "rep_total": 1
        }]
        
        preview_mode = self.navigation_bar.is_preview_mode()
        advanced_mode = self.navigation_bar.is_advanced_user_mode()
        
        self.protocol_runner.set_preview_mode(preview_mode)
        
        self.protocol_runner.set_repeat_protocol_n(1)
        self.protocol_runner.set_run_order(run_order)
        
        self.protocol_runner.set_advanced_hardware_mode(advanced_mode, preview_mode)
        
        self.protocol_runner.start()
        
        self.navigation_bar.btn_play.setText(ICON_PAUSE)
        self.navigation_bar.btn_play.setToolTip("Pause Protocol")

        self._update_navigation_buttons_state()
        
        self.tree.clearSelection()
        self._last_selected_step_id = None
        self._last_published_step_id = None
        
    def stop_protocol(self):
        self.protocol_runner.stop()
        self.clear_highlight()
        self.reset_status_bar()
        self._protocol_running = False

        self._disable_phase_navigation()

        self.navigation_bar.btn_play.setText(ICON_PLAY)
        self.navigation_bar.btn_play.setToolTip("Play Protocol")

        self._update_navigation_buttons_state()
        self._update_ui_enabled_state()
        
        QTimer.singleShot(10, self._cleanup_after_protocol_operation)

    def reset_status_bar(self):
        self.status_bar.lbl_total_time.setText("Total Time: 0.00 s")
        self.status_bar.lbl_step_time.setText("Step Time: 0.00 s")
        self.status_bar.lbl_step_progress.setText("Step 0/0")
        self.status_bar.lbl_step_repetition.setText("Repetition 0/0")
        self.status_bar.lbl_recent_step.setText("Most Recent Step: -")
        self.status_bar.lbl_next_step.setText("Next Step: -")
        self.status_bar.lbl_repeat_protocol_status.setText("1/")

    def _update_ui_enabled_state(self):
        enabled = not self._protocol_running
        
        # allow scrolling but not editing and selection
        if enabled:
            self.tree.setEnabled(True)
            self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
            self.tree.setSelectionMode(QTreeView.ExtendedSelection)
        else:
            self.tree.setEnabled(True)
            self.tree.setContextMenuPolicy(Qt.NoContextMenu)
            self.tree.setSelectionMode(QTreeView.NoSelection)
        
        self.btn_add_step.setEnabled(enabled)
        self.btn_add_step_into.setEnabled(enabled)
        self.btn_add_group.setEnabled(enabled)
        self.btn_add_group_into.setEnabled(enabled)
        self.btn_import.setEnabled(enabled)
        self.btn_import_into.setEnabled(enabled)
        self.btn_export.setEnabled(enabled)

    def _update_navigation_buttons_state(self):
        # Enable navigation buttons if:
        # 1. Protocol is not running, OR
        # 2. Protocol is running/paused AND advanced user mode is enabled
        advanced_mode = self.navigation_bar.is_advanced_user_mode()
        enabled = not self._protocol_running or (self._protocol_running and advanced_mode)
        
        self.navigation_bar.btn_first.setEnabled(enabled)
        self.navigation_bar.btn_prev.setEnabled(enabled)
        self.navigation_bar.btn_next.setEnabled(enabled)
        self.navigation_bar.btn_last.setEnabled(enabled)
        
        checkbox_enabled = not self._protocol_running
        self.navigation_bar.set_preview_mode_enabled(checkbox_enabled)
        self.navigation_bar.set_advanced_user_mode_enabled(checkbox_enabled)
    
    def _navigate_during_protocol(self, target_step_path):
        """navigation during protocol execution in advanced user mode."""
        if not self._protocol_running:
            return False
        
        advanced_mode = self.navigation_bar.is_advanced_user_mode()
        if not advanced_mode:
            return False
        
        success = self.protocol_runner.jump_to_step_by_path(target_step_path)
        if success:
            logger.info(f"Successfully navigated to step at path {target_step_path} during protocol execution")
            
            # only select the step during pause, clear selection during play
            if self.protocol_runner.is_paused():
                self._select_step_by_path(target_step_path)
            else:
                self.tree.clearSelection()
                self._last_selected_step_id = None
                self._last_published_step_id = None
        
        return success
    
    def _enable_phase_navigation(self):
        self.navigation_bar.split_play_button_to_phase_controls()
        self._update_phase_navigation_buttons()

    def _disable_phase_navigation(self):
        self.navigation_bar.merge_phase_controls_to_play_button()

    def navigate_previous_phase(self):
        if self.protocol_runner.navigate_to_previous_phase():
            self._update_phase_navigation_buttons()

    def navigate_next_phase(self):
        if self.protocol_runner.navigate_to_next_phase():
            self._update_phase_navigation_buttons()

    def _update_phase_navigation_buttons(self):
        phase_info = self.protocol_runner.get_phase_navigation_info()
        
        current_phase = phase_info["current_phase"]
        total_phases = phase_info["total_phases"]
        
        prev_enabled = current_phase > 1
        next_enabled = current_phase < total_phases
        
        self.navigation_bar.set_phase_navigation_enabled(prev_enabled, next_enabled)

    def _get_all_step_paths(self):
        step_paths = []

        def collect_steps_recursive(parent_item, current_path):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row, 0)
                if not item:
                    continue

                item_path = current_path + [row]
                row_type = item.data(ROW_TYPE_ROLE)
                if row_type == STEP_TYPE:
                    step_paths.append(item_path)
                elif row_type == GROUP_TYPE:
                    collect_steps_recursive(item, item_path)

        collect_steps_recursive(self.model.invisibleRootItem(), [])
        return step_paths     

    def _get_current_step_index(self):
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return -1
        
        current_path = selected_paths[0]
        current_item = self.get_item_by_path(current_path)
        if not current_item or current_item.data(ROW_TYPE_ROLE) != STEP_TYPE:
            return -1
        
        all_step_paths = self._get_all_step_paths()
        try:
            return all_step_paths.index(current_path)
        except ValueError:
            return -1
        
    def _select_step_by_path(self, path):
        if not path:
            return
        
        self.tree.clearSelection()
        index = self.model.index(path[0], 0)
        for row in path[1:]:
            if index.isValid():
                index = self.model.index(row, 0, index)
            else:
                return
            
        if index.isValid():
            self.tree.selectionModel().select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
            self.tree.scrollTo(index)

    def _add_step_at_root_and_select(self):
        scroll_pos = self.save_scroll_positions()
        self.state.snapshot_for_undo()

        new_step = ProtocolStep(
            parameters = dict(step_defaults),
            name = "Step"
        )
        self.state.assign_uid_to_step(new_step)
        self.state.sequence.append(new_step)
        self.reassign_ids()
        self.load_from_state()

        all_step_paths = self._get_all_step_paths()
        if all_step_paths:
            root_step_paths = [path for path in all_step_paths if len(path) == 1]
            if root_step_paths:
                self._select_step_by_path(root_step_paths[-1])

        self.restore_scroll_positions(scroll_pos)
        self._mark_protocol_modified()

    def add_step_to_current_group(self):
        if self._protocol_running:
            return        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return        
        current_path = selected_paths[0]
        current_item = self.get_item_by_path(current_path)        
        if not current_item:
            return        
        if current_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
            if not self._is_last_step_in_group(current_path):
                return
            
            scroll_pos = self.save_scroll_positions()
            self.state.snapshot_for_undo()    

            new_step = ProtocolStep(
                parameters=dict(step_defaults),
                name="Step"
            )  
            self.state.assign_uid_to_step(new_step)  

            if len(current_path) == 1:
                target_elements = self.state.sequence
                insert_position = current_path[0] + 1
            else:
                parent_path = current_path[:-1]
                target_elements = self._find_elements_by_path(parent_path)
                insert_position = current_path[-1] + 1
            
            target_elements.insert(insert_position, new_step)        
            self.reassign_ids()
            self.load_from_state()
            if len(current_path) == 1:
                new_step_path = [insert_position]
            else:
                new_step_path = current_path[:-1] + [insert_position]
            
            self._select_step_by_path(new_step_path)
            self.restore_scroll_positions(scroll_pos)
            
        elif current_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
            if not self._group_has_direct_steps(current_item):
                scroll_pos = self.save_scroll_positions()
                self.state.snapshot_for_undo()
                
                new_step = ProtocolStep(
                    parameters=dict(step_defaults),
                    name="Step"
                )
                self.state.assign_uid_to_step(new_step) 
                
                target_elements = self._find_elements_by_path(current_path)
                target_elements.append(new_step)                
                self.reassign_ids()
                self.load_from_state()                
                new_step_path = current_path + [0]
                self._select_step_by_path(new_step_path)
                self.restore_scroll_positions(scroll_pos)

        self._mark_protocol_modified()

    def _is_last_step_in_group(self, step_path):
        if not step_path:
            return False
        
        if len(step_path) == 1:
            parent_item = self.model.invisibleRootItem()
            parent_path = []
        else:
            parent_path = step_path[:-1]
            parent_item = self.get_item_by_path(parent_path)
        
        if not parent_item:
            return False
        
        step_index = step_path[-1]        
        step_indices = []
        for row in range(parent_item.rowCount()):
            item = parent_item.child(row, 0)
            if item and item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                step_indices.append(row)
        
        return step_indices and step_index == step_indices[-1]
    
    def _group_has_direct_steps(self, group_item):
        if not group_item or group_item.data(ROW_TYPE_ROLE) != GROUP_TYPE:
            return False        
        for row in range(group_item.rowCount()):
            child_item = group_item.child(row, 0)
            if child_item and child_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                return True        
        return False
    
    def _find_step_by_uid(self, uid):
        """returns (item, path) tuple or (None, None) if not found."""
        def search_recursive(parent_item, current_path):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row, 0)
                if not item:
                    continue
                
                item_path = current_path + [row]
                row_type = item.data(ROW_TYPE_ROLE)                
                if row_type == STEP_TYPE:
                    step_uid = item.data(Qt.UserRole + 1000 + hash("UID") % 1000) or ""
                    if step_uid == uid:
                        return item, item_path
                elif row_type == GROUP_TYPE:
                    result = search_recursive(item, item_path)
                    if result[0] is not None:
                        return result
                                
            return None, None  
              
        return search_recursive(self.model.invisibleRootItem(), [])
    
    def _step_exists_by_uid(self, step_uid):
        if not step_uid:
            return False
        
        def search_recursive(parent_item):
            for row in range(parent_item.rowCount()):
                desc_item = parent_item.child(row, 0)
                if not desc_item:
                    continue
                    
                if desc_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                    stored_uid = desc_item.data(Qt.UserRole + 1000 + hash("UID") % 1000)
                    if stored_uid == step_uid:
                        return True
                elif desc_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                    if search_recursive(desc_item):
                        return True
            return False
        
        return search_recursive(self.model.invisibleRootItem())

    def _get_last_published_step_uid(self):
        if not hasattr(self, '_last_published_step_uid'):
            self._last_published_step_uid = None
        return self._last_published_step_uid

    def _set_last_published_step_uid(self, step_uid):
        self._last_published_step_uid = step_uid

    def _handle_step_removal_cleanup(self):
        """check if published step still exists."""
        if self._processing_device_viewer_message or self._protocol_running:
            return
        
        last_published_uid = self._get_last_published_step_uid()
        if not last_published_uid:
            return
        
        if not self._step_exists_by_uid(last_published_uid):
            
            selected_paths = self.get_selected_paths()
            published_something = False
            
            if selected_paths:
                for path in selected_paths:
                    item = self.get_item_by_path(path)
                    if item and item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                        step_id = self._publish_step_message(item, path, editable=True)
                        if step_id:
                            self._last_selected_step_id = step_id
                            self._last_published_step_id = step_id
                            # update the stored UID
                            step_uid = item.data(Qt.UserRole + 1000 + hash("UID") % 1000)
                            self._set_last_published_step_uid(step_uid)
                            published_something = True
                            break
            
            if not published_something:
                self._send_empty_device_state_message()
                self._last_selected_step_id = None
                self._last_published_step_id = None
                self._set_last_published_step_uid(None)
    
    def _send_empty_device_state_message(self):
        empty_msg = DeviceViewerMessageModel(
            channels_activated={},
            routes=[],
            id_to_channel={},
            step_info={"step_id": None, "step_label": None, "free_mode": True},
            editable=True
        )
        publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=empty_msg.serialize())
        
        # clear last published UID
        self._set_last_published_step_uid(None)

    def _publish_step_message(self, step_item, step_path, editable=True):
        if not step_item or step_item.data(ROW_TYPE_ROLE) != STEP_TYPE:
            return None
        
        parent = step_item.parent() or self.model.invisibleRootItem()
        row = step_item.row()
        id_col = protocol_grid_fields.index("ID")
        desc_col = protocol_grid_fields.index("Description")
        id_item = parent.child(row, id_col)
        desc_item = parent.child(row, desc_col)
        step_id = id_item.text() if id_item else ""
        step_description = desc_item.text() if desc_item else "Step"
        
        device_state = step_item.data(Qt.UserRole + 100)
        if not device_state:
            device_state = DeviceState()
        
        step_uid = step_item.data(Qt.UserRole + 1000 + hash("UID") % 1000) or ""
        
        msg_model = device_state_to_device_viewer_message(
            device_state, step_uid, step_description, step_id, editable
        )
        publish_message(topic=PROTOCOL_GRID_DISPLAY_STATE, message=msg_model.serialize())
        
        # update last published UID
        self._set_last_published_step_uid(step_uid)
        
        return step_id
        
    def _apply_id_to_channel_mapping_to_all_steps(self, new_id_to_channel_mapping, new_route_colors):
        
        def update_steps_recursive(parent_item):
            for row in range(parent_item.rowCount()):
                item = parent_item.child(row, 0)
                if not item:
                    continue
                    
                row_type = item.data(ROW_TYPE_ROLE)
                if row_type == STEP_TYPE:
                    current_device_state = item.data(Qt.UserRole + 100)
                    if current_device_state:
                        # update only the id_to_channel mapping
                        current_device_state.update_id_to_channel_mapping(new_id_to_channel_mapping, new_route_colors)
                        item.setData(current_device_state, Qt.UserRole + 100)
                    else:
                        new_device_state = DeviceState(
                            activated_electrodes={},
                            paths=[],
                            id_to_channel=new_id_to_channel_mapping.copy(),
                            route_colors=new_route_colors.copy() if new_route_colors else []
                        )
                        item.setData(new_device_state, Qt.UserRole + 100)
                elif row_type == GROUP_TYPE:
                    update_steps_recursive(item)
        
        update_steps_recursive(self.model.invisibleRootItem())
        
        self.update_step_dev_fields()
    # ---------------------------------------------------------------------------
    def _is_checkbox_checked(self, item_or_value):
        """standardize checkbox state checking across all scenarios."""
        if item_or_value is None:
            return False
        
        # if it is a QStandardItem, get checkbox state
        if hasattr(item_or_value, 'data'):
            check_state = item_or_value.data(Qt.CheckStateRole)
            if check_state is not None:
                return check_state == Qt.Checked or check_state == 2
            # Fallback to text-based checking
            text_value = item_or_value.text()
            return str(text_value).strip().lower() in ("1", "true", "yes", "on")
        
        # other direct value checks
        if isinstance(item_or_value, bool):
            return item_or_value
        if isinstance(item_or_value, int):
            return item_or_value == 1 or item_or_value == 2 or item_or_value == Qt.Checked
        if isinstance(item_or_value, str):
            return item_or_value.strip().lower() in ("1", "true", "yes", "on")
        
        return False

    def _normalize_checkbox_value(self, value):
        """convert any checkbox value to standardized string format for protocol state."""
        return "1" if self._is_checkbox_checked(value) else "0"
    
    def _handle_checkbox_change(self, parent, row, field):
        if field == "Video":
            video_col = protocol_grid_fields.index("Video")
            video_item = parent.child(row, video_col)
            if video_item:
                checked = self._is_checkbox_checked(video_item)
                video_item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
                
        elif field == "Magnet":
            magnet_col = protocol_grid_fields.index("Magnet")
            magnet_height_col = protocol_grid_fields.index("Magnet Height")
            magnet_item = parent.child(row, magnet_col)
            magnet_height_item = parent.child(row, magnet_height_col)
            
            if not magnet_item or not magnet_height_item:
                return

            checked = self._is_checkbox_checked(magnet_item)
            magnet_item.setData(Qt.Checked if checked else Qt.Unchecked, Qt.CheckStateRole)
            
            if checked:
                last_value = magnet_height_item.data(Qt.UserRole + 2)
                if last_value is None or last_value == "":
                    last_value = "0"
                magnet_height_item.setEditable(True)
                magnet_height_item.setText(str(last_value))
                self.model.dataChanged.emit(magnet_height_item.index(), magnet_height_item.index(), [Qt.EditRole])
            else:
                current_value = magnet_height_item.text()
                if current_value:
                    magnet_height_item.setData(current_value, Qt.UserRole + 2)
                magnet_height_item.setEditable(False)
                magnet_height_item.setText("")
                self.model.dataChanged.emit(magnet_height_item.index(), magnet_height_item.index(), [Qt.EditRole])

            self.model.itemChanged.emit(magnet_height_item)

    def create_buttons(self):
        self.button_layout_1 = QHBoxLayout()
        
        self.btn_add_step = QPushButton("Add Step")
        self.btn_add_step_into = QPushButton("Add Step Into")
        self.btn_add_group = QPushButton("Add Group")
        self.btn_add_group_into = QPushButton("Add Group Into")
        
        self.btn_add_step.clicked.connect(self.add_step)
        self.btn_add_step_into.clicked.connect(self.add_step_into)
        self.btn_add_group.clicked.connect(self.add_group)
        self.btn_add_group_into.clicked.connect(self.add_group_into)
        
        self.button_layout_1.addWidget(self.btn_add_step)
        self.button_layout_1.addWidget(self.btn_add_step_into)
        self.button_layout_1.addWidget(self.btn_add_group)
        self.button_layout_1.addWidget(self.btn_add_group_into)
        self.button_layout_1.addStretch()
        
        self.button_layout_2 = QHBoxLayout()
        
        self.btn_import = QPushButton("Import from JSON")
        self.btn_import_into = QPushButton("Import Into")
        self.btn_export = QPushButton("Export to JSON")
        
        self.btn_import.clicked.connect(self.import_from_json)
        self.btn_import_into.clicked.connect(self.import_into_json)
        self.btn_export.clicked.connect(self.export_to_json)
        
        self.button_layout_2.addWidget(self.btn_import)
        self.button_layout_2.addWidget(self.btn_import_into)
        self.button_layout_2.addWidget(self.btn_export)
        self.button_layout_2.addStretch()
        
    def setup_header_context_menu(self):
        header = self.tree.header()
        header.setContextMenuPolicy(Qt.CustomContextMenu)
        header.customContextMenuRequested.connect(self.show_column_toggle_dialog)

    def on_selection_changed(self):
        if hasattr(self, '_processing_device_viewer_message') and self._processing_device_viewer_message:
            return
        if self._programmatic_change:
            return            
        if self._protocol_running:
            return
        selected_paths = self.get_selected_paths()

        has_selection = len(selected_paths) > 0
        if not self._protocol_running:
            self.btn_add_step_into.setEnabled(has_selection)
            self.btn_add_group_into.setEnabled(has_selection)
            self.btn_import_into.setEnabled(has_selection)

        current_step_id = None
        current_step_uid = None
        
        if has_selection:
            path = selected_paths[0]
            item = self.get_item_by_path(path)
            if item and item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                # step info
                parent = item.parent() or self.model.invisibleRootItem()
                row = item.row()
                id_col = protocol_grid_fields.index("ID")
                id_item = parent.child(row, id_col)
                current_step_id = id_item.text() if id_item else ""
                current_step_uid = item.data(Qt.UserRole + 1000 + hash("UID") % 1000)
                
                # publish only if this is a different step
                if current_step_id != self._last_published_step_id:
                    published_step_id = self._publish_step_message(item, path, editable=True)
                    if published_step_id:
                        self._last_published_step_id = published_step_id
        
        # check if transitioned from a step selected to NO step selected
        if self._last_selected_step_id and not current_step_id and not self._navigating:
            self._send_empty_device_state_message()
            self._last_published_step_id = None            
        
        self._last_selected_step_id = current_step_id
        
    def save_column_settings(self):
        for i, field in enumerate(protocol_grid_fields):
            self._column_visibility[field] = not self.tree.isColumnHidden(i)
            self._column_widths[field] = self.tree.header().sectionSize(i)
            
    def restore_column_settings(self):
        for i, field in enumerate(protocol_grid_fields):
            if field in self._column_visibility:
                self.tree.setColumnHidden(i, not self._column_visibility[field])
            if field in self._column_widths and self._column_widths[field] > 0:
                self.tree.setColumnWidth(i, self._column_widths[field])
        
    def ensure_minimum_protocol(self):
        if not self.state.sequence:
            default_step = ProtocolStep(
                parameters=dict(step_defaults),
                name="Step"
            )
            self.state.assign_uid_to_step(default_step)
            self.state.sequence.append(default_step)
            self.reassign_ids()
            
    def reassign_ids(self):
        def assign_ids_recursive(elements, parent_prefix=""):
            step_counter = 1
            group_counter = ord('A')
            
            for element in elements:
                if isinstance(element, ProtocolStep):
                    if parent_prefix:
                        element.parameters["ID"] = f"{parent_prefix}_{step_counter}"
                    else:
                        element.parameters["ID"] = str(step_counter)
                    step_counter += 1
                    
                elif isinstance(element, ProtocolGroup):
                    if parent_prefix:
                        group_id = f"{parent_prefix}_{chr(group_counter)}"
                    else:
                        group_id = chr(group_counter)
                    
                    element.parameters["ID"] = group_id
                    group_counter += 1
                    
                    assign_ids_recursive(element.elements, group_id)
                    
        assign_ids_recursive(self.state.sequence)
        
    def setup_context_menu(self):
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self.show_context_menu)
        
    def show_context_menu(self, pos):
        menu = EditContextMenu(self)
        global_pos = self.tree.mapToGlobal(pos)
        menu.exec(global_pos)
        
    def setup_shortcuts(self):
        shortcuts = [
            (QKeySequence.Delete, self._protected_delete_selected),
            (QKeySequence("Ctrl+C"), self._protected_copy_selected),
            (QKeySequence("Ctrl+X"), self._protected_cut_selected),
            (QKeySequence("Ctrl+V"), self._protected_paste_selected),
            (QKeySequence("Ctrl+Z"), self._protected_undo_last),
            (QKeySequence("Ctrl+Y"), self._protected_redo_last),
            (QKeySequence("Ctrl+Shift+Y"), self._protected_redo_last),
            (QKeySequence("Ctrl+A"), self._protected_select_all),
            (QKeySequence("Ctrl+D"), self._protected_deselect_rows),
            (QKeySequence("Ctrl+I"), self._protected_invert_row_selection),
            (QKeySequence("Insert"), self._protected_insert_step),
            (QKeySequence("Ctrl+Insert"), self._protected_insert_group),
            (QKeySequence("Ctrl+Shift+V"), self._protected_paste_into),
            (QKeySequence("A"), self.navigate_to_first_step),
            (QKeySequence("S"), self.navigate_to_previous_step),
            (QKeySequence("D"), self.navigate_to_next_step),
            (QKeySequence("F"), self.navigate_to_last_step),
            (QKeySequence("E"), self._protected_add_step_to_current_group),
        ]
        
        for key_seq, slot in shortcuts:
            shortcut = QShortcut(key_seq, self)
            shortcut.activated.connect(slot)

    # protected wrapper methods for keyboard shortcuts
    def _protected_delete_selected(self):
        if not self._protocol_running:
            self.delete_selected()

    def _protected_copy_selected(self):
        if not self._protocol_running:
            self.copy_selected()

    def _protected_cut_selected(self):
        if not self._protocol_running:
            self.cut_selected()

    def _protected_paste_selected(self):
        if not self._protocol_running:
            self.paste_selected()

    def _protected_undo_last(self):
        if not self._protocol_running:
            self.undo_last()

    def _protected_redo_last(self):
        if not self._protocol_running:
            self.redo_last()

    def _protected_select_all(self):
        if not self._protocol_running:
            self.select_all()

    def _protected_deselect_rows(self):
        if not self._protocol_running:
            self.deselect_rows()

    def _protected_invert_row_selection(self):
        if not self._protocol_running:
            self.invert_row_selection()

    def _protected_insert_step(self):
        if not self._protocol_running:
            self.insert_step()

    def _protected_insert_group(self):
        if not self._protocol_running:
            self.insert_group()

    def _protected_paste_into(self):
        if not self._protocol_running:
            self.paste_into()

    def _protected_add_step_to_current_group(self):
        if not self._protocol_running:
            self.add_step_to_current_group()
            
    def show_column_toggle_dialog(self):
        dialog = ColumnToggleDialog(self)
        dialog.exec()
        
    def _delayed_sync(self):
        """Delayed synchronization to avoid excessive updates."""
        if not self._programmatic_change:
            self.sync_to_state()
            
    def sync_to_state(self):
        """Immediately sync model to state."""
        if hasattr(self, '_processing_device_viewer_message') and self._processing_device_viewer_message:
            return
        if not self._programmatic_change:
            # dont sync during protocol running
            if self._protocol_running:
                if not self.navigation_bar.is_advanced_user_mode():
                    return
            
            self.model_to_state()
            self.protocolChanged.emit()

            if not getattr(self, '_loading_from_file', False) and not self._protocol_running:
                self._mark_protocol_modified()
            
    def model_to_state(self):
        if self._protocol_running and not self.navigation_bar.is_advanced_user_mode():
            return
            
        self.state.sequence.clear()
        
        def convert_recursive(parent_item, target_list):
            for row in range(parent_item.rowCount()):
                desc_item = parent_item.child(row, 0)
                if not desc_item:
                    continue
                    
                row_type = desc_item.data(ROW_TYPE_ROLE)
                
                parameters = {}
                for col, field in enumerate(protocol_grid_fields):
                    item = parent_item.child(row, col)
                    if not item:
                        continue
                        
                    if field in ("Video", "Magnet"):
                        check_state = item.data(Qt.CheckStateRole)
                        if check_state is not None:
                            checked = check_state == Qt.Checked or check_state == 2
                            parameters[field] = "1" if checked else "0"
                        else:
                            parameters[field] = "0"
                    elif field == "Magnet Height":
                        stored_value = item.data(Qt.UserRole + 2)
                        if stored_value is not None and stored_value != "":
                            parameters[field] = str(stored_value)
                        else:
                            parameters[field] = item.text()
                    else:
                        parameters[field] = item.text()
                
                uid = desc_item.data(Qt.UserRole + 1000 + hash("UID") % 1000)
                if uid:
                    parameters["UID"] = str(uid)
                
                if row_type == STEP_TYPE:
                    step = ProtocolStep(parameters=parameters, name=parameters.get("Description", "Step"))
                    
                    device_state = desc_item.data(Qt.UserRole + 100)
                    if device_state:
                        step.device_state = device_state
                    else:
                        step.device_state = DeviceState()
                    
                    target_list.append(step)
                    
                elif row_type == GROUP_TYPE:
                    allowed_group_fields = {
                        "Description", "ID", "Repetitions", "Duration", "Run Time",
                        "Voltage", "Frequency", "Trail Length"
                    }
                    filtered_parameters = {}
                    for field, value in parameters.items():
                        if field in allowed_group_fields and value.strip():
                            filtered_parameters[field] = value
                    
                    group = ProtocolGroup(
                        parameters=filtered_parameters,
                        name=filtered_parameters.get("Description", "Group")
                    )
                    
                    convert_recursive(desc_item, group.elements)
                    target_list.append(group)
                    
        convert_recursive(self.model.invisibleRootItem(), self.state.sequence)
        
    def save_selection(self):
        """Save current selection state."""
        selected_paths = self.get_selected_paths()
        return selected_paths
        
    def restore_selection(self, saved_paths):
        """Restore selection state."""
        if not saved_paths:
            return
            
        selection_model = self.tree.selectionModel()
        selection_model.clear()
        
        for path in saved_paths:
            index = self.model.index(path[0], 0)
            for row in path[1:]:
                if index.isValid():
                    index = self.model.index(row, 0, index)
                else:
                    break
                    
            if index.isValid():
                selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
        
    def save_scroll_positions(self):
        return (
            self.tree.verticalScrollBar().value(),
            self.tree.horizontalScrollBar().value()
        )

    def restore_scroll_positions(self, positions):
        vert, horiz = positions
        QTimer.singleShot(0, lambda: self.tree.verticalScrollBar().setValue(vert))
        QTimer.singleShot(0, lambda: self.tree.horizontalScrollBar().setValue(horiz))

    def load_from_state(self):
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        self.save_column_settings()        
        self._programmatic_change = True
        self._loading_from_file = True
        try:
            self.state.assign_uids_to_all_steps()
            self.state_to_model()
            self.setup_headers()
            self.tree.expandAll()
            self.update_all_group_aggregations()
            self.update_step_dev_fields()
        finally:
            self._programmatic_change = False
            self._loading_from_file = False
            
        self.restore_column_settings()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
            
    def state_to_model(self):
        self.model.clear()        
        self.model.setHorizontalHeaderLabels(protocol_grid_fields)
        
        def add_recursive(elements, parent_item):
            for element in elements:
                if isinstance(element, ProtocolStep):
                    row_items = make_row(step_defaults, element.parameters, STEP_TYPE)
                    row_items[0].setData(element.device_state, Qt.UserRole + 100)
                    parent_item.appendRow(row_items)                    
                elif isinstance(element, ProtocolGroup):
                    allowed_group_fields = {
                        "Description", "ID", "Repetitions", "Duration", "Run Time",
                        "Voltage", "Frequency", "Trail Length", "UID"
                    }
                    
                    filtered_group_parameters = {}
                    for field, value in element.parameters.items():
                        if field in allowed_group_fields:
                            filtered_group_parameters[field] = value
                    
                    row_items = make_row(group_defaults, filtered_group_parameters, GROUP_TYPE)
                    parent_item.appendRow(row_items)
                    # Recursively add children
                    add_recursive(element.elements, row_items[0])
                    
        add_recursive(self.state.sequence, self.model.invisibleRootItem())
        self.setup_headers()
        
    def setup_headers(self):
        for i, width in enumerate(protocol_grid_column_widths):
            self.tree.setColumnWidth(i, width)

    def _is_advanced_mode_field_editable(self, field):
        return field in ("Voltage", "Frequency")
            
    def on_item_changed(self, item):
        if self._programmatic_change:
            return
        if self._protocol_running:
            if self.navigation_bar.is_advanced_user_mode():
                parent = item.parent() or self.model.invisibleRootItem()
                col = item.column()
                if col < len(protocol_grid_fields):
                    field = protocol_grid_fields[col]
                    if self._is_advanced_mode_field_editable(field):
                        logger.debug(f"Allowing advanced mode edit of field: {field}")
                        
                        # handle immediate voltage/frequency publishing for advanced mode
                        if field in ("Voltage", "Frequency"):
                            self._handle_advanced_mode_voltage_frequency_edit(item, parent, field)
                    else:
                        return
                else:
                    return
            else:
                return
            
        if not getattr(self, "_undo_snapshotted", False):
            self.state.snapshot_for_undo()
            self._undo_snapshotted = True
        parent = item.parent() or self.model.invisibleRootItem()
        row = item.row()
        col = item.column()
        if col >= len(protocol_grid_fields):
            return

        field = protocol_grid_fields[col]

        if field in ("Video", "Magnet"):
            self._handle_checkbox_change(parent, row, field)
            if not self._protocol_running or (self._protocol_running and self.navigation_bar.is_advanced_user_mode() and self._is_advanced_mode_field_editable(field)):
                self.sync_to_state()
            QTimer.singleShot(0, self._reset_undo_snapshotted)
            return

        desc_item = parent.child(row, 0)

        if desc_item and desc_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
            self.update_single_step_dev_fields(desc_item, changed_field=field)

        if field in ("Voltage", "Frequency", "Trail Length"):
            if desc_item and desc_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                self._set_field_for_group(desc_item, field, item.text())
            if not self._block_aggregation:
                self._update_parent_aggregations(parent)

        if field in ("Duration", "Run Time"):
            self._update_parent_aggregations(parent)

        if field in ("Duration", "Repeat Duration", "Volume Threshold"):
            self._validate_numeric_field(item, field)

        if field in ("Trail Length", "Trail Overlay"):
            self._handle_trail_fields(parent, row)

        if not self._protocol_running or (self._protocol_running and self.navigation_bar.is_advanced_user_mode() and self._is_advanced_mode_field_editable(field)):
            self.sync_to_state()
        QTimer.singleShot(0, self._reset_undo_snapshotted)

    def _handle_advanced_mode_voltage_frequency_edit(self, item, parent, field):
        """Handle voltage/frequency edits in advanced mode during protocol execution."""
        if not self._protocol_running or not self.navigation_bar.is_advanced_user_mode():
            return
        
        # get the step item and extract UID
        desc_item = parent.child(item.row(), 0)
        if not desc_item or desc_item.data(ROW_TYPE_ROLE) != STEP_TYPE:
            return
        
        step_uid = desc_item.data(Qt.UserRole + 1000 + hash("UID") % 1000)
        if not step_uid:
            return
        
        # get current voltage and frequency values from the row
        voltage_col = protocol_grid_fields.index("Voltage")
        frequency_col = protocol_grid_fields.index("Frequency")
        
        voltage_item = parent.child(item.row(), voltage_col)
        frequency_item = parent.child(item.row(), frequency_col)
        
        voltage_str = voltage_item.text() if voltage_item else "100.0"
        frequency_str = frequency_item.text() if frequency_item else "10000"
        
        # validate values
        voltage = VoltageFrequencyService.validate_voltage(voltage_str)
        frequency = VoltageFrequencyService.validate_frequency(frequency_str)
        
        # update the protocol runner execution plan and publish if needed
        preview_mode = self.navigation_bar.is_preview_mode()
        success = self.protocol_runner.update_step_voltage_frequency_in_plan(
            step_uid, voltage, frequency
        )        
        if success:
            logger.info(f"Advanced mode edit: Updated step {step_uid} to {voltage}V, {frequency}Hz")
        
    def _set_field_for_group(self, group_item, field, value):
        """Recursively set a field for all steps and subgroups under a group, and set the group row's own value."""
        self._block_aggregation = True
        try:
            idx = protocol_grid_fields.index(field)
            parent_item = group_item.parent()
            if parent_item is None:
                parent_item = self.model.invisibleRootItem()
            group_row_item = parent_item.child(group_item.row(), idx)
            if group_row_item:
                group_row_item.setText(value)
            for row in range(group_item.rowCount()):
                desc_item = group_item.child(row, 0)
                if not desc_item:
                    continue
                row_type = desc_item.data(ROW_TYPE_ROLE)
                if row_type == STEP_TYPE:
                    item = group_item.child(row, idx)
                    if item:
                        item.setText(value)
                elif row_type == GROUP_TYPE:
                    self._set_field_for_group(desc_item, field, value)
        finally:
            self._block_aggregation = False
            
    def _validate_numeric_field(self, item, field):
        """Validate numeric fields."""
        try:
            value = float(item.text())
            if field == "Volume Threshold":
                item.setText(f"{value:.2f}")
            elif field in ("Duration", "Repeat Duration", "Run Time"):
                item.setText(f"{value:.1f}")
            else:
                item.setText(f"{value:.1f}")
        except ValueError:
            if field == "Volume Threshold":
                item.setText("0.00")
            else:
                item.setText("0.0")
            
    def _handle_trail_fields(self, parent, row):
        try:
            trail_length_col = protocol_grid_fields.index("Trail Length")
            overlay_col = protocol_grid_fields.index("Trail Overlay")
            
            trail_length_item = parent.child(row, trail_length_col)
            overlay_item = parent.child(row, overlay_col)
            
            if trail_length_item and overlay_item:
                trail_length = int(trail_length_item.text())
                max_overlay = max(0, trail_length - 1)
                overlay_val = int(overlay_item.text())
                
                if overlay_val > max_overlay:
                    overlay_item.setText(str(max_overlay))
        except (ValueError, IndexError):
            pass
            
    def _update_parent_aggregations(self, parent):
        current = parent
        while current and current != self.model.invisibleRootItem():
            if current.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                row = current.row()
                parent_item = current.parent() or current.model().invisibleRootItem()
                group_items = [parent_item.child(row, c) for c in range(parent_item.columnCount())]
                children_rows = [
                    [current.child(r, c) for c in range(current.columnCount())]
                    for r in range(current.rowCount())
                ]
                calculate_group_aggregation_from_children(group_items, children_rows)
            current = current.parent()

    def _calculate_estimated_repeat_duration(self, device_state, repetitions, duration, trail_length, trail_overlay):
        if not device_state.has_paths():
            return 0.0
        
        has_loops = any(len(path) >= 2 and path[0] == path[-1] for path in device_state.paths)
        if not has_loops:
            return 0.0
        
        max_loop_duration = 0.0
        
        for path in device_state.paths:
            is_loop = len(path) >= 2 and path[0] == path[-1]
            if not is_loop:
                continue
            
            effective_length = len(path) - 1
            step_size = trail_length - trail_overlay
            
            if step_size <= 0:
                cycle_length = effective_length
            else:
                phases = 0
                position = 0
                while position < effective_length:
                    phases += 1
                    position += step_size
                    if position >= effective_length:
                        break
                cycle_length = phases
            
            single_cycle_duration = cycle_length * duration
            
            if repetitions > 1:
                loop_duration = (repetitions - 1) * single_cycle_duration + single_cycle_duration + duration  # +1 for return phase
            else:
                loop_duration = single_cycle_duration + duration
            
            max_loop_duration = max(max_loop_duration, loop_duration)
        
        return max_loop_duration
            
    def update_single_step_dev_fields(self, desc_item, changed_field=None):
        if not desc_item or desc_item.data(ROW_TYPE_ROLE) != STEP_TYPE:
            return
            
        parent = desc_item.parent() or self.model.invisibleRootItem()
        row = desc_item.row()
        
        try:
            repetitions_col = protocol_grid_fields.index("Repetitions")
            duration_col = protocol_grid_fields.index("Duration")
            repeat_duration_col = protocol_grid_fields.index("Repeat Duration")
            trail_length_col = protocol_grid_fields.index("Trail Length")
            trail_overlay_col = protocol_grid_fields.index("Trail Overlay")
            max_path_col = protocol_grid_fields.index("Max. Path Length")
            run_time_col = protocol_grid_fields.index("Run Time")
            
            repetitions_item = parent.child(row, repetitions_col)
            duration_item = parent.child(row, duration_col)
            repeat_duration_item = parent.child(row, repeat_duration_col)
            trail_length_item = parent.child(row, trail_length_col)
            trail_overlay_item = parent.child(row, trail_overlay_col)
            max_path_item = parent.child(row, max_path_col)
            run_time_item = parent.child(row, run_time_col)
            
            if not all([repetitions_item, duration_item, repeat_duration_item, 
                    trail_length_item, trail_overlay_item, max_path_item, run_time_item]):
                return
                
            device_state = desc_item.data(Qt.UserRole + 100)
            if not device_state:                
                device_state = DeviceState()
                desc_item.setData(device_state, Qt.UserRole + 100)
                
            repetitions = int(repetitions_item.text() or "1")
            duration = float(duration_item.text() or "1.0")
            current_repeat_duration = float(repeat_duration_item.text() or "0.0")
            trail_length = int(trail_length_item.text() or "1")
            trail_overlay = int(trail_overlay_item.text() or "0")
            
            estimated_repeat_duration = self._calculate_estimated_repeat_duration(
                device_state, repetitions, duration, trail_length, trail_overlay
            )
            
            should_update_repeat_duration = changed_field != "Repeat Duration" and self._protocol_running == False 
            
            if should_update_repeat_duration:
                repeat_duration_to_use = estimated_repeat_duration
            else:
                repeat_duration_to_use = current_repeat_duration
            
            max_path_length = device_state.longest_path_length()
            run_time = device_state.calculated_duration(duration, repetitions, repeat_duration_to_use, 
                                                    trail_length, trail_overlay)
            
            self._programmatic_change = True
            try:
                max_path_item.setText(str(max_path_length))
                run_time_item.setText(f"{run_time:.1f}")
                
                if should_update_repeat_duration:
                    repeat_duration_item.setText(f"{estimated_repeat_duration:.1f}")
                    
            finally:
                self._programmatic_change = False
                
        except (ValueError, IndexError):
            pass
            
    def update_step_dev_fields(self):
        def update_recursive(parent):
            for row in range(parent.rowCount()):
                desc_item = parent.child(row, 0)
                if desc_item:
                    if desc_item.data(ROW_TYPE_ROLE) == STEP_TYPE:
                        # pass None as changed_field
                        self.update_single_step_dev_fields(desc_item, changed_field=None)
                    elif desc_item.hasChildren():
                        update_recursive(desc_item)
                        
        update_recursive(self.model.invisibleRootItem())
        
    def update_all_group_aggregations(self):
        def update_recursive(parent):
            for row in range(parent.rowCount()):
                item = parent.child(row, 0)
                if item and item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
                    group_items = [parent.child(row, c) for c in range(parent.columnCount())]
                    children_rows = [
                        [item.child(r, c) for c in range(item.columnCount())]
                        for r in range(item.rowCount())
                    ]
                    calculate_group_aggregation_from_children(group_items, children_rows)
                    if item.hasChildren():
                        update_recursive(item)
        update_recursive(self.model.invisibleRootItem())
        
    def get_selected_paths(self):
        paths = []
        selection = self.tree.selectionModel().selectedRows(0)
        for index in selection:
            path = []
            current = index
            while current.isValid():
                path.insert(0, current.row())
                current = current.parent()
            paths.append(path)
        return paths
        
    def get_item_by_path(self, path):
        item = self.model.invisibleRootItem()
        for row in path:
            if row < item.rowCount():
                item = item.child(row, 0)
            else:
                return None
        return item
        
    def _find_elements_by_path(self, path):
        elements = self.state.sequence
        for i in path:
            if i < len(elements):
                if isinstance(elements[i], ProtocolGroup):
                    elements = elements[i].elements
                else:
                    return elements
            else:
                return []
        return elements
        
    def select_all(self):
        self.tree.selectAll()
        
    def deselect_rows(self):
        self.tree.clearSelection()
        
    def invert_row_selection(self):
        selection_model = self.tree.selectionModel()
        all_indexes = []
        
        def collect_indexes(parent_index):
            for row in range(self.model.rowCount(parent_index)):
                index = self.model.index(row, 0, parent_index)
                all_indexes.append(index)
                if self.model.hasChildren(index):
                    collect_indexes(index)
                    
        collect_indexes(self.model.index(-1, -1))  # Root
        
        # Get currently selected rows
        selected_rows = set()
        for index in selection_model.selectedRows(0):
            selected_rows.add((index.row(), index.parent()))
            
        selection_model.clear()
        
        # Select all non-selected rows
        for index in all_indexes:
            if (index.row(), index.parent()) not in selected_rows:
                selection_model.select(index, QItemSelectionModel.Select | QItemSelectionModel.Rows)
                
    def insert_step(self):
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = 0
        else:
            target_path = selected_paths[0]
            if len(target_path) == 1:
                target_elements = self.state.sequence
                row = target_path[0]
            else:
                parent_path = target_path[:-1]
                target_elements = self._find_elements_by_path(parent_path)
                row = target_path[-1]
                
        self.state.snapshot_for_undo()
        
        new_step = ProtocolStep(
            parameters=dict(step_defaults),
            name="Step"
        )
        self.state.assign_uid_to_step(new_step)
        target_elements.insert(row, new_step)
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        self._mark_protocol_modified()
        
    def insert_group(self):
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = 0
        else:
            target_path = selected_paths[0]
            if len(target_path) == 1:
                target_elements = self.state.sequence
                row = target_path[0]
            else:
                parent_path = target_path[:-1]
                target_elements = self._find_elements_by_path(parent_path)
                row = target_path[-1]
                
        self.state.snapshot_for_undo()
        
        new_group = ProtocolGroup(
            parameters=dict(group_defaults),
            name="Group"
        )
        target_elements.insert(row, new_group)
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        self._mark_protocol_modified()
        
    def add_step(self):
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = len(target_elements)
        else:
            target_path = selected_paths[0]
            target_item = self.get_item_by_path(target_path)
            if not target_item:
                return
            parent_path = target_path[:-1]
            target_elements = self._find_elements_by_path(parent_path)
            row = target_path[-1] + 1
                
        self.state.snapshot_for_undo()
        
        new_step = ProtocolStep(
            parameters=dict(step_defaults),
            name="Step"
        )
        self.state.assign_uid_to_step(new_step)
        target_elements.insert(row, new_step)
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        self._mark_protocol_modified()
        
    def add_step_into(self):
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if not target_item:
            return
            
        self.state.snapshot_for_undo()
        
        new_step = ProtocolStep(
            parameters=dict(step_defaults),
            name="Step"
        )
        self.state.assign_uid_to_step(new_step)
        
        if target_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
            target_elements = self._find_elements_by_path(target_path)
            target_elements.append(new_step)
        else:
            parent_path = target_path[:-1]
            target_elements = self._find_elements_by_path(parent_path)
            row = target_path[-1] + 1
            target_elements.insert(row, new_step)
            
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        self._mark_protocol_modified()
        
    def add_group(self):
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = len(target_elements)
        else:
            target_path = selected_paths[0]
            target_item = self.get_item_by_path(target_path)
            if not target_item:
                return
            parent_path = target_path[:-1]
            target_elements = self._find_elements_by_path(parent_path)
            row = target_path[-1] + 1
                
        self.state.snapshot_for_undo()
        
        new_group = ProtocolGroup(
            parameters=dict(group_defaults),
            name="Group"
        )
        target_elements.insert(row, new_group)
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        self._mark_protocol_modified()
        
    def add_group_into(self):
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if not target_item:
            return
            
        self.state.snapshot_for_undo()
        
        new_group = ProtocolGroup(
            parameters=dict(group_defaults),
            name="Group"
        )
        
        if target_item.data(ROW_TYPE_ROLE) == GROUP_TYPE:
            target_elements = self._find_elements_by_path(target_path)
            target_elements.append(new_group)
        else:
            parent_path = target_path[:-1]
            target_elements = self._find_elements_by_path(parent_path)
            row = target_path[-1] + 1
            target_elements.insert(row, new_group)
            
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        self._mark_protocol_modified()
        
    def delete_selected(self):
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        self.state.snapshot_for_undo()
        
        selected_paths.sort(reverse=True)
        
        for path in selected_paths:
            target_elements = self._find_elements_by_path(path[:-1])
            if target_elements and 0 <= path[-1] < len(target_elements):
                target_elements.pop(path[-1])
        
        self.ensure_minimum_protocol()
        
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        
        QTimer.singleShot(0, self._handle_step_removal_cleanup)
        self._mark_protocol_modified()
        
    def copy_selected(self):
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
        
        def is_descendant(path, other_path):
            return len(path) > len(other_path) and path[:len(other_path)] == other_path

        filtered_paths = []
        for path in selected_paths:
            is_child = False
            for i in selected_paths:
                if i != path and is_descendant(path, i):
                    is_child = True
                    break
            if not is_child:
                filtered_paths.append(path)
            
        copied_items = []
        for path in filtered_paths:
            if len(path) == 1:
                if path[0] < len(self.state.sequence):
                    copied_items.append(copy.deepcopy(self.state.sequence[path[0]]))
            else:
                parent_path = path[:-1]
                elements = self._find_elements_by_path(parent_path)
                if path[-1] < len(elements):
                    copied_items.append(copy.deepcopy(elements[path[-1]]))
                    
        self._clipboard = copied_items
        
    def cut_selected(self):
        self.copy_selected()
        
        # store current state before deletion for cleanup
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
        
        self.delete_selected()
        
    def paste_selected(self, above=True):
        if not hasattr(self, '_clipboard') or not self._clipboard:
            return
            
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            target_elements = self.state.sequence
            row = 0 if above else len(target_elements)
        else:
            path = selected_paths[0]
            target_elements = self._find_elements_by_path(path[:-1])
            row = path[-1] + (0 if above else 1)
            
        self.state.snapshot_for_undo()
        
        for i, item in enumerate(copy.deepcopy(self._clipboard)):
            if hasattr(item, 'parameters') and 'UID' in item.parameters:
                self.state.assign_uid_to_step(item)
            target_elements.insert(row + i, item)
            
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        
        QTimer.singleShot(0, self._handle_step_removal_cleanup)
        self._mark_protocol_modified()
        
    def paste_into(self):
        if not hasattr(self, '_clipboard') or not self._clipboard:
            return
            
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if not target_item or target_item.data(ROW_TYPE_ROLE) != GROUP_TYPE:
            return
            
        target_elements = self._find_elements_by_path(target_path)
        
        self.state.snapshot_for_undo()
        
        for item in copy.deepcopy(self._clipboard):
            target_elements.append(item)
            
        self.reassign_ids()
        self.load_from_state()
        # self.sync_to_state()
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        self._mark_protocol_modified()
        
    def undo_last(self):
        self._programmatic_change = True
        if self.state.undo_stack:
            self.state.undo()
            self.load_from_state()
        self._programmatic_change = False
        self._mark_protocol_modified()
            
    def redo_last(self):
        self._programmatic_change = True
        if self.state.redo_stack:
            self.state.redo()
            self.load_from_state()
        self._programmatic_change = False
        self._mark_protocol_modified()

    def _reset_undo_snapshotted(self):
        self._undo_snapshotted = False
        
    def export_to_json(self):
        if self._protocol_running:
            return
        
        # use experiment directory as default save location
        default_dir = str(self.experiment_manager.get_experiment_directory())
        
        file_name, _ = QFileDialog.getSaveFileName(self, "Export Protocol to JSON", default_dir, "JSON Files (*.json)")
        if file_name:
            try:
                # check if saving to experiment directory
                if self.experiment_manager.is_save_in_experiment_directory(file_name):
                    # cleanup existing JSONs first
                    self.experiment_manager.cleanup_experiment_jsons()
                    logger.info("Overwriting existing JSONs in experiment directory")
                
                flat_data = self.state.to_flat_export()
                with open(file_name, "w") as f:
                    json.dump(flat_data, f, indent=2)
                
                # update protocol state tracker
                self.protocol_state_tracker.set_saved_protocol(file_name)
                self._update_protocol_display()
                
            except Exception as e:
                logger.info(self, "Export Error", f"Failed to export: {str(e)}")
                
    def import_from_json(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Import Protocol from JSON", "", "JSON Files (*.json)")
        if file_name:
            try:
                with open(file_name, "r") as f:
                    data = json.load(f)
                
                # flag to prevent marking as modified during an import
                self._loading_from_file = True
                try:
                    self.state.from_flat_export(data)
                    self.load_from_state()
                    
                    # update protocol state tracker
                    self.protocol_state_tracker.set_loaded_protocol(file_name)
                    self._update_protocol_display()
                    
                finally:
                    self._loading_from_file = False
                    
            except Exception as e:
                QMessageBox.warning(self, "Import Error", f"Failed to import: {str(e)}")
                
    def import_into_json(self):
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        selected_paths = self.get_selected_paths()
        if not selected_paths:
            return
            
        target_path = selected_paths[0]
        target_item = self.get_item_by_path(target_path)
        if target_item is None:
            return
            
        file_name, _ = QFileDialog.getOpenFileName(self, "Import Protocol from JSON", "", "JSON Files (*.json)")
        if not file_name:
            return
            
        try:
            with open(file_name, "r") as f:
                data = json.load(f)
            
            self.state.snapshot_for_undo()

            imported_state = ProtocolState()      
            imported_state.from_flat_export(data)
            
            # assign new UIDs to ALL imported elements to prevent conflicts
            self._assign_new_uids_to_all_elements(imported_state.sequence)
            
            target_item_type = target_item.data(ROW_TYPE_ROLE)
            
            if target_item_type == GROUP_TYPE:
                target_elements = self._find_elements_by_path(target_path)
                
                for element in imported_state.sequence:
                    target_elements.append(element)
                                    
            elif target_item_type == STEP_TYPE:
                if len(target_path) == 1: # root-level step
                    target_elements = self.state.sequence
                    insert_position = target_path[0] + 1
                else: # step inside a group                    
                    parent_path = target_path[:-1]
                    target_elements = self._find_elements_by_path(parent_path)
                    insert_position = target_path[-1] + 1
                
                # insert AFTER the selected step
                for i, element in enumerate(imported_state.sequence):
                    target_elements.insert(insert_position + i, element)
                                
            else:
                return
            
            self.reassign_ids()
            self.load_from_state()
            # self.sync_to_state()
            self.restore_scroll_positions(scroll_pos)
            self.restore_selection(saved_selection)
            
            QTimer.singleShot(0, self._handle_step_removal_cleanup)
            self._mark_protocol_modified()
            
        except Exception as e:
            QMessageBox.warning(self, "Import Error", f"Failed to import: {str(e)}")

    def _assign_new_uids_to_all_elements(self, elements):
        for element in elements:
            if isinstance(element, ProtocolStep):
                element.parameters["UID"] = str(self.state.get_next_uid())
            elif isinstance(element, ProtocolGroup):
                self._assign_new_uids_to_all_elements(element.elements)

    def _reset_palette_change_flag(self):
        self._processing_palette_change = False

    def _refresh_model_after_theme_change(self):
        if self._protocol_running:
            return            
        
        scroll_pos = self.save_scroll_positions()
        saved_selection = self.save_selection()
        
        self._programmatic_change = True
        try:
            self._clean_group_parameters_recursive(self.state.sequence)            
            # reload model from clean state
            self.load_from_state()            
        finally:
            self._programmatic_change = False
            
        self.restore_scroll_positions(scroll_pos)
        self.restore_selection(saved_selection)
        
    def event(self, event):
        if event.type() == QEvent.PaletteChange:
            self._processing_palette_change = True
            try:                
                self.clear_highlight()
                if hasattr(self, 'navigation_bar'):
                    self.navigation_bar.update_theme_styling()
                if hasattr(self, 'information_panel'):
                    self.information_panel.update_theme_styling()

                QTimer.singleShot(50, self._refresh_model_after_theme_change)
            finally:
                QTimer.singleShot(100, self._reset_palette_change_flag)
        return super().event(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("Protocol Grid Widget")
    window.setGeometry(50, 50, 1400, 500)    
    widget = PGCWidget()
    window.setCentralWidget(widget)    
    window.show()    
    sys.exit(app.exec())