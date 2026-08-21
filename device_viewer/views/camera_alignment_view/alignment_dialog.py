"""The combined Camera Alignment window, as TraitsUI MVC.

One modeless split-screen window replacing the two former popups:
the endpoint pane (device SVG, scene coordinates) on the left and
the device-outline pane (captured camera frame, camera pixels) on
the right, so the ground truth and the marked start points are
placed side by side. The green Confirm Alignment button between
them is the macro that commits everything: it saves the endpoint,
stages the outline points, and fires alignment_confirmed for the
owner to run Go To Endpoint. Nothing closes the window — the user
iterates freely and closes when done.

The three pieces live separately in this module:

- CameraAlignmentModel — the state: the two pane models (each
  rendering through its own TraitsUI view), readiness, the buttons,
  and the alignment_confirmed event.
- camera_alignment_dialog_view — the module-level View: the pane
  split, the chevron-revealed settings sidebar (the TraitsUI
  subpanel from alignment_settings), and the button row.
- CameraAlignmentController — the wiring: pane readiness to the
  model, live overlay restyling from the settings model, and the
  Confirm/Close behavior."""

from traits.api import (
    Bool,
    Button,
    Event,
    HasTraits,
    Instance,
    observe,
)
from traitsui.api import (
    Controller,
    Group,
    HGroup,
    HSplit,
    InstanceEditor,
    UItem,
    VGroup,
    View,
    spring,
)

from logger.logger_service import get_logger
from microdrop_style.button_styles import (
    SUCCESS_BUTTON_STYLE,
    TEXT_BUTTON_STYLE,
)
from microdrop_style.icons.icons import (
    ICON_CHEVRON_LEFT,
    ICON_CHEVRON_RIGHT,
)
from microdrop_utils.color_helpers import rgb_to_hex
from microdrop_utils.traitsui_qt_helpers import IconToggleEditor

from .alignment_panes import EndpointPane, OutlinePane
from .alignment_settings import (
    COLOR_SETTING_TRAITS,
    SETTING_TRAITS,
    AlignmentSettingsModel,
    alignment_settings_view,
)

logger = get_logger(__name__)


#: The window's opening size — room for both panes at a useful zoom.
START_WIDTH_PX = 1500
START_HEIGHT_PX = 820
SIDEBAR_WIDTH_PX = 280

#: The Confirm Alignment macro button: the standard green success
#: look, but with a real-word text font (the success style inherits
#: the Material Symbols icon font, which TEXT_BUTTON_STYLE overrides).
CONFIRM_BUTTON_STYLE = f"{SUCCESS_BUTTON_STYLE}\n{TEXT_BUTTON_STYLE}"


# ------------------------------ Model ----------------------------- #
class CameraAlignmentModel(HasTraits):
    """The window's state. The panes arrive fully built (the owner
    observes their save/accept events); they render through the
    view's InstanceEditor items."""

    #: The two pane models (each carries its own TraitsUI view).
    endpoint_pane = Instance(EndpointPane)
    outline_pane = Instance(OutlinePane)

    #: The sidebar's model (persists through the preferences).
    settings = Instance(AlignmentSettingsModel)

    #: True once the outline pane has a real camera frame — gates
    #: Confirm Alignment.
    outline_ready = Bool(False)

    #: Reveals the settings sidebar.
    options_visible = Bool(False)

    confirm = Button("Confirm Alignment")
    close = Button("Close")

    #: Fires AFTER Confirm Alignment has saved the endpoint and
    #: staged the outline points (the pane signals fire first,
    #: synchronously) — the owner responds by running Go To
    #: Endpoint.
    alignment_confirmed = Event()


# ------------------------------ View ------------------------------ #
camera_alignment_dialog_view = View(
    VGroup(
        HGroup(
            HSplit(
                UItem("endpoint_pane", style="custom", editor=InstanceEditor()),
                UItem("outline_pane", style="custom", editor=InstanceEditor()),
                springy=True,
            ),
            # The sidebar reveal: a vertical chevron bar, like the
            # device viewer's and the fluorescence image viewer's.
            VGroup(
                UItem(
                    "options_visible",
                    editor=IconToggleEditor(
                        on_glyph=ICON_CHEVRON_RIGHT,
                        off_glyph=ICON_CHEVRON_LEFT,
                        tooltip="Hide or show the snap and "
                        "quad-style settings sidebar",
                    ),
                    springy=True,
                ),
            ),
            VGroup(
                UItem(
                    "settings",
                    style="custom",
                    editor=InstanceEditor(view=alignment_settings_view),
                    width=SIDEBAR_WIDTH_PX,
                ),
                visible_when="options_visible",
            ),
        ),
        HGroup(
            spring,
            Group(
                UItem(
                    "confirm",
                    enabled_when="outline_ready",
                    tooltip="Save the endpoint, use the marked "
                    "outline points, and run Go To "
                    "Endpoint",
                ),
                style_sheet=CONFIRM_BUTTON_STYLE,
            ),
            spring,
            UItem("close"),
        ),
        # Real-word buttons — keep them out of the Material Symbols
        # icon font the themed QPushButton rules use. The panes'
        # glyph buttons restyle themselves individually.
        style_sheet=TEXT_BUTTON_STYLE,
    ),
    title="Camera Alignment",
    width=START_WIDTH_PX,
    height=START_HEIGHT_PX,
    resizable=True,
)


# --------------------------- Controller --------------------------- #
class CameraAlignmentController(Controller):
    """Wires the pane widgets to the model and view: readiness
    gating, live overlay restyling from the settings model, the
    Confirm Alignment macro, and Close."""

    model = Instance(CameraAlignmentModel)

    def init(self, info):
        # The pane may already be ready when the window opens — the
        # observer below only fires on changes.
        self.model.outline_ready = self.model.outline_pane.is_ready

        return super().init(info)

    # ------------------------------------------------------------------ #
    @observe("model:outline_pane:is_ready")
    def _on_outline_ready(self, event):
        self.model.outline_ready = event.new

    @observe(", ".join(f"model:settings:{name}" for name in SETTING_TRAITS))
    def _on_setting_changed(self, event):
        """A sidebar edit (or Reset to Defaults): restyle the
        overlays live — the settings model has already persisted
        it."""
        model = self.model
        name, value = event.name, event.new

        if name == "endpoint_snap_radius_px":
            model.endpoint_pane.set_snap_radius(value)
        elif name == "outline_snap_radius_px":
            model.outline_pane.set_snap_radius(value)
        else:
            if name in COLOR_SETTING_TRAITS:
                value = rgb_to_hex(value)

            model.endpoint_pane.set_appearance(**{name: value})
            model.outline_pane.set_appearance(**{name: value})

    # ------------------------------------------------------------------ #
    def object_confirm_changed(self, info):
        """The macro: save the endpoint, stage the outline points,
        then let the owner run Go To Endpoint."""
        if not info.initialized:
            return

        model = self.model
        model.endpoint_pane.save = True
        model.outline_pane.save = True
        model.alignment_confirmed = True

    def object_close_changed(self, info):
        if not info.initialized:
            return

        info.ui.dispose()
