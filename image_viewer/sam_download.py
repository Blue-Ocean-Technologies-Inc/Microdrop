# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Cancellable SAM model-weight download dialog for the
image viewer's automatic ROI identification feature.

Ported from labelme's droplet_roi/download.py progress-dialog widget.
"""

# Third-party imports.
from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import QProgressDialog

# Local imports.
from .analysis import sam_detect

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


class _Cancelled(Exception):
    pass


class _DownloadThread(QThread):
    UNKNOWN_SIZE = -1

    progress = Signal(int, int, str, int, int)
    succeeded = Signal()
    error = Signal(Exception)

    def __init__(self, model_type, parent):
        super().__init__(parent)
        self._model_type = model_type
        self._total_files = sum(
            1 + len(blob.attachments) for blob in model_type._blobs.values()
        )

    def cancel(self):
        self.requestInterruption()

    def run(self):
        file_index = -1
        current_filename = None

        def _on_progress(filename, bytes_so_far, bytes_total):
            nonlocal file_index, current_filename
            if self.isInterruptionRequested():
                raise _Cancelled()
            if filename != current_filename:
                file_index += 1
                current_filename = filename
            self.progress.emit(
                file_index,
                self._total_files,
                filename,
                bytes_so_far,
                bytes_total if bytes_total is not None else self.UNKNOWN_SIZE,
            )

        try:
            self._model_type.pull(progress=_on_progress)
            self.succeeded.emit()
        except _Cancelled:
            pass
        except Exception as e:
            self.error.emit(e)


def _format_bytes(n):
    UNIT = 1024
    value = float(n)
    # Advance a tier when the value rounds up to a full UNIT, so the display
    # never reads "1024 KB" / "1024.0 MB". The boundary rounds to a whole unit
    # (round(value)), independent of each tier's display precision. TB is the
    # terminal unit.
    for suffix, decimals in (("B", 0), ("KB", 0), ("MB", 1), ("GB", 1)):
        if round(value) < UNIT:
            return f"{value:.{decimals}f} {suffix}"
        value /= UNIT
    return f"{value:.1f} TB"


def model_is_cached(model_name):
    """Whether the model's weights are already in the osam cache."""
    if not sam_detect.sam_available():
        raise RuntimeError("osam is not installed")
    return (
        sam_detect.osam.apis.get_model_type_by_name(model_name).get_size() is not None
    )


def download_ai_model(model_name, parent=None):
    if not sam_detect.sam_available():
        raise RuntimeError("osam is not installed")

    if model_is_cached(model_name):
        return True

    model_type = sam_detect.osam.apis.get_model_type_by_name(model_name)

    dialog = QProgressDialog(
        f"Downloading {model_name}...\n(requires internet connection)",
        "Cancel",
        0,
        0,
        parent,
    )
    dialog.setWindowModality(Qt.WindowModality.WindowModal)
    dialog.setMinimumDuration(0)
    dialog.setMinimumWidth(400)
    dialog.setAutoClose(False)
    dialog.setAutoReset(False)

    thread = _DownloadThread(model_type=model_type, parent=parent)
    succeeded = False

    def _on_progress(file_index, file_count, filename, bytes_so_far, bytes_total):
        if succeeded:
            return
        label = (
            f"Downloading {model_name} ({file_index + 1}/{file_count})\n\n{filename}\n"
        )
        if bytes_total != _DownloadThread.UNKNOWN_SIZE:
            dialog.setRange(0, bytes_total)
            dialog.setValue(bytes_so_far)
            label += f"{_format_bytes(bytes_so_far)} / {_format_bytes(bytes_total)}"
        else:
            dialog.setRange(0, 0)
            if bytes_so_far > 0:
                label += _format_bytes(bytes_so_far)
        dialog.setLabelText(label)

    def _on_succeeded():
        nonlocal succeeded
        succeeded = True
        dialog.close()

    def _on_error(e):
        logger.error(f"Model download failed: {e}")
        dialog.setRange(0, 1)
        dialog.setLabelText(
            f"Failed to download {model_name}.\n(check internet connection)"
        )
        dialog.setCancelButtonText("Close")

    dialog.canceled.connect(thread.cancel)
    thread.progress.connect(_on_progress)
    thread.succeeded.connect(_on_succeeded)
    thread.error.connect(_on_error)

    dialog.show()
    thread.start()
    dialog.exec()

    thread.progress.disconnect(_on_progress)
    thread.succeeded.disconnect(_on_succeeded)
    thread.error.disconnect(_on_error)
    if not thread.wait(5000):
        thread.terminate()
        thread.wait()

    return succeeded
