import platform

from envisage.ui.tasks.api import PreferencesPane, PreferencesCategory
from traitsui.api import View, Item, Group, EnumEditor
from apptools.preferences.api import PreferencesHelper
from traits.api import Str, Bool, Enum, List, Range, observe

from device_viewer.utils.camera import supported_qt_video_codec_names
from logger.logger_service import get_logger

logger = get_logger(__name__)

from device_viewer.consts import (
    FFMPEG_CONTAINERS,
    FFMPEG_DEFAULT_CRF,
    FFMPEG_PRESETS,
    FFMPEG_VIDEO_CODECS,
    QT_RECORDER_FORMAT_MKV,
    QT_RECORDER_FORMAT_MP4,
    RECORDER_BACKEND_FFMPEG,
    RECORDER_BACKEND_QT,
    RECORDING_4K_MIN_HEIGHT,
    RECORDING_60FPS_MIN_FPS,
    RECORDING_BITRATE_CLASSES,
    RECORDING_BITRATE_TIERS,
)
from microdrop_style.text_styles import preferences_group_style_sheet
from microdrop_utils.preferences_UI_helpers import create_item_label_group

os_name = platform.system()

if os_name == "Windows":
    default_video_format = "NV12"
    strict_video_format = True

elif os_name == "Linux":
    default_video_format = "JPEG"
    strict_video_format = True

elif os_name == "Darwin":
    default_video_format = "NV12"
    strict_video_format = True

else:
    strict_video_format = False
    default_video_format = "JPEG"


def _bitrate_tier_label(tier: str, mbps: float) -> str:
    """Dropdown entry text: the tier with its bitrate and one-minute file
    size, so the size estimate is always in sight and can never go stale."""
    megabytes_per_minute = mbps * 60 / 8
    return (f"{tier} — {mbps:g} Mbps "
            f"(≈ {megabytes_per_minute:,.0f} MB per minute)")


class CameraPreferences(PreferencesHelper):
    """The preferences helper, inspired by envisage one for the Attractors application.
    The underlying preference object is the global default since we do not pass a
    Preference object. See source code for PreferencesHelper for more details."""

    #### 'PreferencesHelper' interface ########################################

    # The path to the preference node that contains the preferences.
    preferences_path = "camera"

    #### Preferences ##########################################################
    selected_camera = Str
    preferred_video_format = Enum("NV12", "JPEG")
    strict_video_format = Bool
    resolution = Str

    #### Recording preferences ################################################
    recorder_backend = Enum(RECORDER_BACKEND_QT, RECORDER_BACKEND_FFMPEG)

    # FFmpeg-process recorder. fps, resolution and pixel format always come
    # from the camera itself, so only encoding choices are exposed.
    ffmpeg_container = Enum(*FFMPEG_CONTAINERS)
    ffmpeg_video_codec = Enum(*FFMPEG_VIDEO_CODECS)
    ffmpeg_preset = Enum(*FFMPEG_PRESETS)
    ffmpeg_crf = Range(low=0, high=51, value=FFMPEG_DEFAULT_CRF)
    ffmpeg_extra_output_args = Str

    # Qt native recorder.
    qt_video_format = Enum(QT_RECORDER_FORMAT_MP4, QT_RECORDER_FORMAT_MKV)

    # Codec name persisted as a plain Str (never validated against the
    # dynamic list, so a stored choice survives backend differences); the
    # dropdown constrains picks to qt_supported_video_codecs_.
    qt_video_codec = Str
    # Codecs the platform backend can encode into the selected container,
    # queried live (the backend reports a reduced set headless). Trailing
    # underscore keeps the list OUT of the preferences node.
    qt_supported_video_codecs_ = List(Str)

    # Per-resolution-class MKV quality tiers (Auto = recommended rate).
    # The class dropdown picks which tier dropdown is shown; at record time
    # the class is matched from the ACTUAL camera resolution/fps (see
    # recording_bitrate_bps).
    qt_bitrate_resolution_class = Enum(*RECORDING_BITRATE_CLASSES)
    qt_bitrate_1080p30_tier = Enum(*RECORDING_BITRATE_TIERS)
    qt_bitrate_1080p60_tier = Enum(*RECORDING_BITRATE_TIERS)
    qt_bitrate_4k30_tier = Enum(*RECORDING_BITRATE_TIERS)
    qt_bitrate_4k60_tier = Enum(*RECORDING_BITRATE_TIERS)

    def _qt_video_codec_default(self):
        if self.qt_video_format == QT_RECORDER_FORMAT_MP4:
            return "H264"
        else:
            return "MPEG1"

    def traits_init(self):
        self._refresh_qt_supported_video_codecs()

    @observe("qt_video_format")
    def _refresh_qt_supported_video_codecs(self, event=None):
        codec_names = supported_qt_video_codec_names(self.qt_video_format)
        self.qt_supported_video_codecs_ = codec_names
        logger.info(f"Video codecs supported for {self.qt_video_format}: "
                    f"{codec_names}")
        if codec_names and self.qt_video_codec not in codec_names:
            if "H264" in codec_names:
                fallback = "H264"
            elif "MPEG4" in codec_names:
                fallback = "MPEG4"
            else:
                fallback = codec_names[0]

            logger.info(f"Video codec {self.qt_video_codec!r} not supported "
                        f"for {self.qt_video_format}; resetting to "
                        f"{fallback!r}")
            self.qt_video_codec = fallback

    def _preferred_video_format_default(self):
        return default_video_format

    def _strict_video_format_default(self):
        return strict_video_format

    #### Recording helpers ####################################################

    def recording_file_extension(self) -> str:
        """Extension of the next recording file — drives the container for
        both backends (ffmpeg muxes by extension; Qt gets the matching
        QMediaFormat as well)."""
        if self.recorder_backend == RECORDER_BACKEND_FFMPEG:
            return f".{self.ffmpeg_container}"
        return (".mkv" if self.qt_video_format == QT_RECORDER_FORMAT_MKV
                else ".mp4")

    def recording_bitrate_class(self, height: int, fps: float) -> str:
        """Nearest configured resolution class for an actual camera format."""
        if height >= RECORDING_4K_MIN_HEIGHT:
            return ("4K @ 60 fps" if fps >= RECORDING_60FPS_MIN_FPS
                    else "4K @ 24/30 fps")
        return ("1080p @ 60 fps" if fps >= RECORDING_60FPS_MIN_FPS
                else "1080p @ 30 fps")

    def recording_bitrate_bps(self, resolution, fps) -> int | None:
        """Configured bitrate (bits/s) for the Qt recorder, or None when the
        Qt encoder should pick (MP4 format, or format/rate unknown)."""
        if (self.qt_video_format != QT_RECORDER_FORMAT_MKV
                or not resolution or not fps):
            return None
        class_label = self.recording_bitrate_class(resolution[1], fps)
        tier_trait, tier_mbps = RECORDING_BITRATE_CLASSES[class_label]
        return int(tier_mbps[getattr(self, tier_trait)] * 1_000_000)


#### Recording preference view pieces #########################################

recorder_backend_item = create_item_label_group(
    "recorder_backend",
    label_text="Recording Engine",
    item_tooltip=(
        "Qt MediaRecorder: the platform's hardware-accelerated encoding "
        "pipeline — zero per-frame Python work, lowest CPU use.\n\n"
        "FFmpeg process: raw camera frames piped to an external ffmpeg — "
        "full control over the encoder at higher CPU cost."
    ),
)

ffmpeg_settings_group = Group(
    create_item_label_group(
        "ffmpeg_container",
        label_text="Container",
        item_tooltip=(
            "mkv: stays recoverable if the app crashes mid-recording.\n"
            "mp4: most widely supported, but corrupts if not closed cleanly."
        ),
    ),
    create_item_label_group(
        "ffmpeg_video_codec",
        label_text="Video Codec",
        item_tooltip=(
            "libx264 (H.264): fastest, plays everywhere.\n"
            "libx265 (H.265): ~half the file size, higher CPU, "
            "less player support."
        ),
    ),
    create_item_label_group(
        "ffmpeg_preset",
        label_text="Preset",
        item_tooltip=(
            "Encoder speed/compression trade-off: faster presets use less "
            "CPU but produce larger files for the same quality."
        ),
    ),
    create_item_label_group(
        "ffmpeg_crf",
        label_text="Quality (CRF)",
        item_tooltip=(
            "Constant Rate Factor: 0 = lossless, 51 = worst. "
            "~17 is visually lossless; lower values mean larger files."
        ),
    ),
    create_item_label_group(
        "ffmpeg_extra_output_args",
        label_text="Extra Output Args",
        item_tooltip=(
            "Advanced: extra ffmpeg output options appended to the command, "
            'e.g. "-tune zerolatency". fps, resolution and pixel format are '
            "set automatically from the camera."
        ),
    ),
    label="FFmpeg Recording",
    show_labels=False,
    show_border=True,
    visible_when=f'recorder_backend == "{RECORDER_BACKEND_FFMPEG}"',
)

# One quality-tier dropdown per resolution class (each tier labeled with
# its bitrate and per-minute file size); only the class-dropdown-selected
# one is shown.
bitrate_tier_items = [
    Item(
        tier_trait,
        show_label=False,
        editor=EnumEditor(values={tier: _bitrate_tier_label(tier, mbps)
                                  for tier, mbps in tier_mbps.items()}),
        visible_when=f'qt_bitrate_resolution_class == "{class_label}"',
    )
    for class_label, (tier_trait, tier_mbps) in
    RECORDING_BITRATE_CLASSES.items()
]

qt_recorder_settings_group = Group(
    create_item_label_group(
        "qt_video_format",
        label_text="Video Format",
        item_tooltip=(
            "MP4: plays everywhere (browsers, editors, OS previews), but "
            "the index is written when recording stops — a crash "
            "mid-recording can leave the file unreadable.\n\n"
            "MKV: written progressively, so the recording stays recoverable "
            "if the app crashes; less universally supported by players and "
            "editors."
        ),
    ),
    create_item_label_group(
        "qt_video_codec",
        label_text="Video Codec",
        item_editor=EnumEditor(name="qt_supported_video_codecs_"),
        item_tooltip=(
            "Video codecs this machine's backend can encode into the "
            "selected format, queried live from Qt. H.264 is the most "
            "widely playable."
        ),
    ),
    Group(
        create_item_label_group(
            "qt_bitrate_resolution_class",
            label_text="Resolution",
            item_tooltip=(
                "Which resolution class's quality tier to edit below. When "
                "a recording starts, the class matching the actual camera "
                "resolution and frame rate is applied."
            ),
        ),
        *bitrate_tier_items,
        label="MKV Quality",
        show_labels=False,
        show_border=True,
        visible_when=f'qt_video_format == "{QT_RECORDER_FORMAT_MKV}"',
    ),
    label="Qt Recording",
    show_labels=False,
    show_border=True,
    visible_when=f'recorder_backend == "{RECORDER_BACKEND_QT}"',
)


video_settings_tab = PreferencesCategory(
    id="microdrop.video_settings.preferences",
    name="Video Settings",
)

class CameraPreferencesPane(PreferencesPane):
    """Device Viewer preferences pane based on enthought envisage's The preferences pane for the Attractors application."""

    #### 'PreferencesPane' interface ##########################################

    # The factory to use for creating the preferences model object.
    model_factory = CameraPreferences

    category = video_settings_tab.id

    ########################################################################################
    video_format_item = create_item_label_group(
        "preferred_video_format", label_text="Preferred Video Format"
    )
    strict_video_format_item = create_item_label_group(
        "strict_video_format", label_text="Strictly Use Only Preferred Video Format?"
    )

    view = View(
        Item("_"),  # Separator
        Group(
            [video_format_item, strict_video_format_item],
            label="Video Format",
            show_labels=False,
            show_border=True,
            style_sheet=preferences_group_style_sheet,
        ),
        Item("_"),  # Separator
        Group(
            recorder_backend_item,
            ffmpeg_settings_group,
            qt_recorder_settings_group,
            label="Video Recording",
            show_labels=False,
            show_border=True,
            style_sheet=preferences_group_style_sheet,
        ),
        Item("_"),  # Separator
    )