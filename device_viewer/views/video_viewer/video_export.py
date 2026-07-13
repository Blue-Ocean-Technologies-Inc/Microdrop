"""Offline export of a recording's device-aligned and/or cropped rendition.

Decodes the recording with ffmpeg, optionally warps every frame through
the sidecar's alignment transform (the same ``get_transformed_frame`` the
live pipeline used — skipped for raw-space exports and recordings with no
sidecar), crops to the model's region-of-interest keyframes (stepwise
over playback time, so the crop can follow the action), and re-encodes.
Runs on a background thread; the GUI only receives progress strings.
"""
import json
import re
import shutil
import subprocess
import threading
from pathlib import Path

from PySide6.QtCore import QObject, QRect, QRectF, Qt, Signal
from PySide6.QtGui import QImage

from logger.logger_service import get_logger

from ...utils.camera import get_transformed_frame, qtransform_deserialize

logger = get_logger(__name__)

#: Used when the container doesn't report a frame rate.
FALLBACK_EXPORT_FPS = 30.0

#: Suffixes of the exported file, next to the source recording.
ALIGNED_EXPORT_SUFFIX = "_aligned.mkv"
CROPPED_EXPORT_SUFFIX = "_cropped.mkv"


def roi_at(roi_keyframes, position_ms):
    """The region holding at ``position_ms`` (stepwise: latest keyframe at
    or before it; times before the first keyframe use the first keyframe's
    region). Mirrors VideoViewerModel.roi_at for use off the GUI thread."""
    if not roi_keyframes:
        return None
    active = roi_keyframes[0][1]
    for keyframe_ms, region in roi_keyframes:
        if keyframe_ms > position_ms:
            break
        active = region
    return active


def _even(value):
    """libx264 requires even dimensions."""
    value = max(2, int(round(value)))
    return value - (value % 2)


class AlignedVideoExporter(QObject):
    """One export job: input recording (+ sidecar when aligned) + ROI
    keyframes -> the aligned and/or cropped video next to the source.
    ``aligned`` says which space the rendition (and its regions) live in:
    the device-aligned scene (warps every frame through the sidecar's
    transform) or the raw frame (no warp — works for ANY video)."""

    progress = Signal(str)
    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, input_path, sidecar, roi_keyframes, aligned=True,
                 ffmpeg_binary="ffmpeg", parent=None):
        super().__init__(parent)
        self._input_path = str(input_path)
        self._aligned = bool(aligned) and sidecar is not None
        suffix = (ALIGNED_EXPORT_SUFFIX if self._aligned
                  else CROPPED_EXPORT_SUFFIX)
        self._output_path = str(Path(input_path).with_suffix("")) + suffix
        self._sidecar = sidecar
        self._roi_keyframes = sorted(roi_keyframes, key=lambda kf: kf[0])
        self._ffmpeg = ffmpeg_binary

    def start(self):
        if not shutil.which(self._ffmpeg):
            self.failed.emit("FFmpeg binary not found.")
            return
        threading.Thread(target=self._run, daemon=True,
                         name="aligned-video-export").start()

    # ------------------------------------------------------------------ #
    # Worker thread                                                        #
    # ------------------------------------------------------------------ #
    def _probe(self):
        """(width, height, fps) — fps is the TRUE average (exact decoded
        frame count / duration). Qt's recorder muxes variable-frame-rate
        streams whose container rate hints are wrong (a 30 fps recording
        advertises 62.5), so any header-derived rate mistimes the output;
        pairing this true average with a passthrough decode keeps the
        export's duration equal to the source's."""
        ffprobe = str(Path(shutil.which(self._ffmpeg)).with_name("ffprobe"))
        result = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0",
             "-count_frames", "-show_entries",
             "stream=width,height,nb_read_frames : format=duration",
             "-of", "default=noprint_wrappers=1", self._input_path],
            capture_output=True, text=True)
        values = dict(line.split("=", 1)
                      for line in result.stdout.splitlines() if "=" in line)
        try:
            width = int(values["width"])
            height = int(values["height"])
            frame_count = int(values["nb_read_frames"])
            duration_s = float(values["duration"])
        except (KeyError, ValueError) as e:
            raise RuntimeError(
                f"Could not probe the recording ({e}): {result.stderr.strip()}")
        fps = (frame_count / duration_s if duration_s > 0
               else FALLBACK_EXPORT_FPS)
        return width, height, fps

    def _run(self):
        decode = encode = None
        try:
            width, height, fps = self._probe()
            if self._aligned:
                transform = qtransform_deserialize(
                    json.dumps(self._sidecar["transform"]))
                bounding = QRectF(*self._sidecar["bounding_rect"])
                scene_rect = QRectF(*self._sidecar["scene_bounding_rect"])
                # Warp canvas at 1:1 scene scale, so ROI scene coordinates
                # map directly onto warped pixels (minus the scene origin).
                warp_size = (_even(scene_rect.width()),
                             _even(scene_rect.height()))
            else:
                # Raw space: no warp — regions are in frame pixels, the
                # "warp" IS the decoded frame.
                transform = bounding = None
                scene_rect = QRectF(0, 0, width, height)
                warp_size = (width, height)
            # Constant output size (a video can't change resolution):
            # the FIRST region's size, or the full frame when no regions.
            if self._roi_keyframes:
                first_region = self._roi_keyframes[0][1]
                output_size = (_even(first_region[2]), _even(first_region[3]))
            else:
                output_size = (_even(warp_size[0]), _even(warp_size[1]))

            decode = subprocess.Popen(
                [self._ffmpeg, "-hide_banner", "-loglevel", "error",
                 "-i", self._input_path,
                 # Emit each REAL frame exactly once: without passthrough,
                 # ffmpeg pads the VFR stream up to its (wrong) container
                 # rate hint with duplicates, stretching the export.
                 "-fps_mode", "passthrough",
                 "-f", "rawvideo", "-pix_fmt", "rgba", "-"],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            encode = subprocess.Popen(
                [self._ffmpeg, "-y", "-hide_banner", "-loglevel", "error",
                 "-f", "rawvideo", "-vcodec", "rawvideo",
                 "-s", f"{output_size[0]}x{output_size[1]}",
                 "-pix_fmt", "rgba", "-r", f"{fps}", "-i", "-",
                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                 "-preset", "medium", "-crf", "18", self._output_path],
                stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE)

            frame_bytes = width * height * 4
            frame_index = 0
            while True:
                chunk = decode.stdout.read(frame_bytes)
                if len(chunk) < frame_bytes:
                    break
                source = QImage(chunk, width, height,
                                QImage.Format_RGBA8888)
                if self._aligned:
                    warped = get_transformed_frame(
                        source, scene_rect, bounding, transform, warp_size)
                else:
                    warped = source
                frame = self._crop_frame(warped, scene_rect, warp_size,
                                         output_size,
                                         frame_index * 1000.0 / fps)
                frame_data = frame.constBits()
                expected_bytes = output_size[0] * output_size[1] * 4
                if frame_data is None or len(frame_data) != expected_bytes:
                    raise RuntimeError(
                        f"Frame {frame_index} produced "
                        f"{0 if frame_data is None else len(frame_data)} "
                        f"bytes (expected {expected_bytes})")
                try:
                    encode.stdin.write(frame_data)
                except OSError:
                    # Windows reports a dead encoder pipe as EINVAL —
                    # surface ffmpeg's actual complaint instead.
                    try:
                        encode.stdin.close()
                        _, err = encode.communicate(timeout=5)
                        detail = err.decode("utf-8", errors="ignore").strip()
                    except Exception:
                        encode.kill()
                        detail = ""
                    raise RuntimeError(
                        f"Encoder exited at frame {frame_index}"
                        + (f": {detail}" if detail
                           else " (no error output captured)"))
                frame_index += 1
                if frame_index % 60 == 0:
                    self.progress.emit(
                        f"Exporting… {frame_index / fps:.0f}s processed")

            decode.stdout.close()
            encode.stdin.close()
            encode.wait()
            if encode.returncode != 0:
                _, err = encode.communicate()
                raise RuntimeError(err.decode("utf-8", errors="ignore")
                                   or "ffmpeg encode failed")
            logger.info(f"Export complete: {self._output_path}")
            self.finished.emit(self._output_path)
        except Exception as e:
            logger.error(f"Aligned export failed: {e}", exc_info=True)
            self.failed.emit(str(e))
        finally:
            for process in (decode, encode):
                if process is not None and process.poll() is None:
                    process.kill()

    def _crop_frame(self, warped, scene_rect, warp_size, output_size,
                    position_ms):
        """Crop the warped frame to the region holding at ``position_ms``
        (scene coords -> warp pixels), scaled to the constant output size."""
        region = roi_at(self._roi_keyframes, position_ms)
        if region is None:
            frame = warped
        else:
            scale_x = warp_size[0] / scene_rect.width()
            scale_y = warp_size[1] / scene_rect.height()
            pixel_rect = QRect(
                int((region[0] - scene_rect.x()) * scale_x),
                int((region[1] - scene_rect.y()) * scale_y),
                max(1, int(region[2] * scale_x)),
                max(1, int(region[3] * scale_y)),
            ).intersected(QRect(0, 0, warp_size[0], warp_size[1]))
            if pixel_rect.isEmpty():
                # A region entirely outside the frame must not silently
                # become "everything": QImage.copy(emptyRect) copies the
                # WHOLE image.
                raise RuntimeError(
                    f"Region of interest {tuple(region)} lies outside the "
                    "aligned frame — redraw it in the viewer")
            frame = warped.copy(pixel_rect)
        if (frame.width(), frame.height()) != output_size:
            frame = frame.scaled(output_size[0], output_size[1],
                                 Qt.AspectRatioMode.IgnoreAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
        if frame.format() != QImage.Format_RGBA8888:
            frame = frame.convertToFormat(QImage.Format_RGBA8888)
        return frame
