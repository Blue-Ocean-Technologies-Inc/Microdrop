# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# sys imports

# Standard library imports.
import os
import pickle
from pathlib import Path

# Third-party imports.
from PySide6.QtCore import Qt

# Enthought library imports.
from envisage.ui.tasks.api import TasksApplication
from envisage.ui.tasks.tasks_application import DEFAULT_STATE_FILENAME
from pyface.image_resource import ImageResource
from pyface.qt import QtWidgets
from pyface.splash_screen import SplashScreen
from pyface.tasks.api import TaskWindowLayout
from traits.api import Bool, Directory, Event, Instance, List, Property, observe
from traits.etsconfig.api import ETSConfig

# Microdrop package imports.
from dropbot_controller.consts import START_DEVICE_MONITORING

# Microdrop utils imports.
from microdrop_utils.dramatiq_pub_sub_helpers import publish_message

# Local imports.
from .consts import CHANGELOG_PATH, EXPERIMENT_DIR
from .helpers import get_microdrop_redis_globals_manager
from .preferences import MicrodropPreferences

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


# set some global consts used application wide.
ETSConfig.company = "Sci-Bots"
ETSConfig.user_data = str(Path.home() / "Documents" / ETSConfig.company / "Microdrop")
ETSConfig.application_home = str(Path(ETSConfig.application_data) / "Microdrop")


def _show_beta_disclaimer():
    """Show beta disclaimer once. Stores a marker file after first display."""
    from microdrop_application.dialogs.pyface_wrapper import disclaimer

    marker = Path(ETSConfig.application_home) / ".beta_disclaimer_accepted"
    if marker.exists():
        return

    disclaimer_text = """
    <b>Microdrop</b> is an open-source <b>beta</b> provided for testing and
    evaluation.<br><br>
    It may contain bugs or unexpected behaviour.<br><br>
    Please validate results in your own workflows and ensure your data is
    properly backed up.<br><br>
    Provided under <b>AGPLv3</b> without warranty. Use at your own risk."""

    disclaimer(None, message=disclaimer_text)

    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("Beta disclaimer accepted.")


def _show_whats_new():
    """Show a What's New dialog with changelog sections added since the last run.

    Mirrors the beta-disclaimer marker pattern: the changelog text as of the
    previous run is cached in application_home/.previous_changelog, anything
    newly prepended to CHANGELOG.md since then (commitizen prepends a section
    per release) is rendered in an information dialog, and the cache is
    refreshed. The first ever run only seeds the cache so users aren't
    greeted with the entire history.
    """
    from microdrop_application.dialogs.pyface_wrapper import information

    from microdrop_utils.markdown_helpers import changelog_sections_added_since
    from microdrop_utils.pyside_helpers import markdown_text_to_html

    if not CHANGELOG_PATH.exists():
        return
    current_changelog = CHANGELOG_PATH.read_text(encoding="utf-8")

    cache = Path(ETSConfig.application_home) / ".previous_changelog"
    if not cache.exists():
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(current_changelog, encoding="utf-8")
        return

    new_sections = changelog_sections_added_since(
        cache.read_text(encoding="utf-8"), current_changelog
    )
    if not new_sections.strip():
        return

    information(
        None, markdown_text_to_html(new_sections), title="What's New?", cancel=False
    )

    cache.write_text(current_changelog, encoding="utf-8")


def describe_dock_widgets(main_window):
    """Describe every dock widget's geometry, for a window pyface refused to save.

    Runs during application shutdown, so it must never raise itself; any
    failure while introspecting the window is returned as text instead.
    """
    try:
        lines = []

        for widget in main_window.findChildren(QtWidgets.QDockWidget):
            geometry = widget.geometry()
            tabified_titles = [
                tabbed.windowTitle()
                for tabbed in main_window.tabifiedDockWidgets(widget)
            ]
            lines.append(
                f"{widget.windowTitle()!r} visible={widget.isVisible()} "
                f"area={main_window.dockWidgetArea(widget)} "
                f"geometry={geometry.x()},{geometry.y()} "
                f"{geometry.width()}x{geometry.height()} "
                f"floating={widget.isFloating()} tabified_with={tabified_titles}"
            )

        return "\n".join(lines)
    except Exception as error:
        return f"Could not describe dock widgets: {error}"


class MicrodropApplication(TasksApplication):
    """Device Viewer application based on enthought envisage's tasks application."""

    #### 'IApplication' interface #############################################

    # The application's globally unique identifier.
    id = "microdrop.frontend.app"

    # The application's user-visible name.
    name = "Microdrop Next Gen"

    #### 'TasksApplication' interface #########################################

    ###### DONE USING ETSConfig NOW ##########################################

    # #: The directory on the local file system used to persist application
    # #: data. Should be same as state_location for convenience.
    # home = application_home_directory
    #
    # #: The directory on the local file system used to persist window layout
    # #: information.
    # state_location = application_home_directory / ".save_state"
    #
    # #: We don't use this directory, but it defaults to "~/enthought" and
    # #: keeps creating it so we set it to our save location
    # user_data = application_home_directory / "Experimental_Data "

    ###########################################################################

    #: The filename that the application uses to persist window layout
    #: information.
    state_filename = DEFAULT_STATE_FILENAME

    # The default window-level layout for the application.
    default_layout = List(TaskWindowLayout)

    # Whether to restore the previous application-level layout on startup.
    always_use_default_layout = Property(Bool)

    # experiments directory
    experiments_directory = Property(Directory)
    current_experiment_directory = Property(Directory)
    experiment_changed = Event()

    # branding
    icon = Instance(ImageResource)
    splash_screen = Instance(SplashScreen)

    #### 'Application' interface ##############################################

    preferences_helper = Instance(MicrodropPreferences)

    ######### Extra 'Application' Events #############################################

    extra_plugins_loaded = Event(
        desc="Trigger if extra plugins are loaded post app initialization"
    )

    ###########################################################################
    # Private interface.
    ###########################################################################

    #### Trait initializers ###################################################

    # note: The _default after a trait name to define a method is a
    # convention to indicate that the trait is a default value for another
    # trait.

    def _default_layout_default(self):
        """
        Trait initializer for the default_layout task, which is the active
        task to be displayed. It is gotten from the preferences.
        """
        active_task = self.preferences_helper.default_task
        tasks = [factory.id for factory in self.task_factories]
        return [TaskWindowLayout(*tasks, active_task=active_task, size=(800, 600))]

    def _preferences_helper_default(self):
        """
        Retrieve the preferences from the preferences file using the
        DeviceViewerPreferences class.
        """
        return MicrodropPreferences(preferences=self.preferences)

    def _icon_default(self):
        icon_path = (
            Path(__file__).parent.parent
            / "microdrop_style"
            / "icons"
            / "Microdrop_Icon.png"
        )
        return ImageResource(str(icon_path))

    def _splash_screen_default(self):
        splash_image_path = (
            Path(__file__).parent.parent
            / "microdrop_style"
            / "icons"
            / "Microdrop_Primary_Logo_FHD.png"
        )

        class _TopMostSplashScreen(SplashScreen):
            """SplashScreen forced to stay on top of every other window.

            A bare ``QSplashScreen`` is frameless and top-level but does NOT carry
            ``WindowStaysOnTopHint``, so while the app boots it can get buried behind
            the task window. We add the hint (and raise/activate on show) so the splash
            always sits at the top level of the application until it's closed.
            """

            def _create_control(self, parent):
                control = super()._create_control(parent)
                # The FHD artwork (1920x1080) overflows small screens
                # (the portable device is 1280x800) and, being always
                # on top, locks the user out of everything under it —
                # cap it at 60% of the available screen and re-centre.
                available = control.screen().availableGeometry()
                target = available.size() * 0.6
                pixmap = control.pixmap()
                if pixmap.width() > target.width() or pixmap.height() > target.height():
                    control.setPixmap(
                        pixmap.scaled(
                            target, Qt.KeepAspectRatio, Qt.SmoothTransformation
                        )
                    )
                    control.move(available.center() - control.rect().center())
                control.setWindowFlags(control.windowFlags() | Qt.WindowStaysOnTopHint)
                control.raise_()
                control.activateWindow()
                return control

        return _TopMostSplashScreen(
            image=ImageResource(str(splash_image_path)),
            text="Microdrop-Next-Gen v.beta",
        )

    #### Trait property getter/setters ########################################

    # the _get and _set tags in the methods are used to define a getter and
    # setter for a trait property.

    def _get_always_use_default_layout(self):
        return self.preferences_helper.always_use_default_layout

    def _get_experiments_directory(self) -> Path:
        return Path(self.preferences_helper.EXPERIMENTS_DIR)

    def _get_current_experiment_directory(self) -> Path:
        # try to get experiment directory from app globals
        globals = get_microdrop_redis_globals_manager()

        current_exp_dir = globals.get("experiment_directory", None)

        if current_exp_dir is None:
            current_exp_dir = EXPERIMENT_DIR
            globals["experiment_directory"] = EXPERIMENT_DIR

        return self.experiments_directory / current_exp_dir

    def _set_current_experiment_directory(self, directory: Path):
        if not isinstance(directory, Path):
            directory = Path(directory)

        globals = get_microdrop_redis_globals_manager()
        globals["experiment_directory"] = directory.stem

        self._get_current_experiment_directory().mkdir(parents=True, exist_ok=True)

        self.experiment_changed = True

    @observe("application_initialized")
    def _on_application_initialized(self, event):
        logger.critical("Application Initialized")
        _show_beta_disclaimer()
        _show_whats_new()

        logger.info("Requesting Dropbot Search")
        publish_message(message="", topic=START_DEVICE_MONITORING)

    ############################# Initialization #############################
    def traits_init(self):
        self.current_experiment_directory.mkdir(parents=True, exist_ok=True)
        logger.info(
            "Initialized microdrop application. Current experiment "
            f"directory: {self.current_experiment_directory}"
        )

    #### Handler for Layout Restore Errors if any ##########################
    def start(self):
        try:
            logger.debug("Starting new Microdrop application instance.")
            return super().start()
        except Exception:
            import traceback

            logger.debug("Error restoring layout, falling back to default layout.")
            traceback.print_exc()

            self.preferences_helper.always_use_default_layout = True

            return super().start()

    #### State persistence: survive layout-extraction failures ##############
    def _save_state(self):
        """Override so a layout pyface cannot serialise never blocks exit.

        ``TasksApplication.exit()`` calls this unguarded via
        ``_prepare_exit()``. Pyface's ``MainWindowLayout.get_layout_for_area``
        (pyface/ui/qt/tasks/main_window_layout.py) raises ``RuntimeError``
        when a dock-widget arrangement can't be expressed as nested
        splitters; left unguarded, that escapes ``exit()`` before any window
        is destroyed, so the window and app never close. Here it degrades to
        "layout not saved" for that window instead.
        """
        window_layouts = []

        for window in self.windows:
            try:
                window_layouts.append(window.get_window_layout())
            except RuntimeError as error:
                logger.warning(
                    f"Could not save window layout for {window!r}: {error}\n"
                    f"{describe_dock_widgets(window.control)}"
                )

        if window_layouts:
            self._state.previous_window_layouts = window_layouts

        filename = os.path.join(self.state_location, self.state_filename)
        logger.debug(f"Saving application state to {filename}")

        try:
            with open(filename, "wb") as f:
                pickle.dump(self._state, f, protocol=self.layout_save_protocol)
        except Exception:
            logger.exception("Error while saving application state")
        else:
            logger.debug("Application state successfully saved")
