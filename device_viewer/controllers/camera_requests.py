# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""The camera requests other plugins send the Device Viewer over pub/sub:
validating each, and handing it to the camera panel — at once, or once the
panel is built after the first paint (#1064)."""

# Standard library imports.
import json

# Third-party imports.
from pydantic import ValidationError

# Enthought library imports.
from pyface.api import GUI

# Local imports.
from ..models.media import (
    CameraControlsRequest,
    CameraSelectSourceRequest,
    CameraSettingsRequest,
)

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)


def parse_camera_controls_request(message):
    """Parse and validate a DEVICE_VIEWER_CAMERA_SET_CONTROLS payload.

    Returns a ``(request, reply)`` pair: on success ``request`` is the
    validated ``CameraControlsRequest`` as a plain dict and ``reply`` is
    None; on failure ``request`` is None and ``reply`` is a ready-to-publish
    ``CameraControlsApplied`` failure payload (``ok=False``), so the caller
    can answer a waiting requester without reaching the camera widget. The
    request_id is recovered from the raw payload when possible, so the
    requester still gets matched even on a failed validation.
    """
    return _parse_camera_request(message, CameraControlsRequest, "camera controls")


def parse_camera_settings_request(message):
    """Parse and validate a DEVICE_VIEWER_CAMERA_APPLY_SETTINGS payload into
    a ``(request, reply)`` pair like parse_camera_controls_request, the
    failure reply being a ``CameraSettingsApplied`` payload."""
    return _parse_camera_request(message, CameraSettingsRequest, "capture settings")


def _parse_camera_request(message, validator_class, description):
    """``(request dict, None)`` for a valid ``validator_class`` payload,
    else ``(None, {request_id, ok=False, error})``."""

    try:
        raw = json.loads(message) if message and message.strip() else {}
    except (json.JSONDecodeError, TypeError) as error:
        logger.warning(f"Unparseable {description} request: {message!r}")

        return None, {"request_id": "", "ok": False, "error": str(error)}

    request_id = str(raw.get("request_id", "")) if isinstance(raw, dict) else ""

    try:
        request = validator_class.model_validate(raw)
    except ValidationError as error:
        logger.warning(f"Invalid {description} request: {message!r} ({error})")

        # Name the field and the reason ("exposure_ms: Input should be
        # greater than 0"), not pydantic's "1 validation error for ..." header.
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or "request"

        return None, {
            "request_id": request_id,
            "ok": False,
            "error": f"{field}: {first['msg']}",
        }

    return request.model_dump(), None


def parse_camera_select_source_request(message):
    """Parse and validate a DEVICE_VIEWER_CAMERA_SELECT_SOURCE payload.

    Returns a ``(request, reply)`` pair like parse_camera_controls_request:
    the validated ``CameraSelectSourceRequest`` as a plain dict and None, or
    None and a ``CameraSourceSelected`` failure payload lacking only
    ``active`` (the camera's state, which the caller knows). The request_id
    and label are recovered from the raw payload when possible.
    """

    try:
        raw = json.loads(message) if message and message.strip() else {}
    except (json.JSONDecodeError, TypeError) as error:
        logger.warning(f"Unparseable camera select_source request: {message!r}")

        return None, {"request_id": "", "label": "", "ok": False, "error": str(error)}

    raw_fields = raw if isinstance(raw, dict) else {}

    try:
        request = CameraSelectSourceRequest.model_validate(raw)
    except ValidationError as error:
        logger.warning(f"Invalid camera select_source request: {message!r} ({error})")

        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"]) or "request"

        return None, {
            "request_id": str(raw_fields.get("request_id", "")),
            "label": str(raw_fields.get("label", "")),
            "ok": False,
            "error": f"{field}: {first['msg']}",
        }

    return request.model_dump(), None


def deliver_to_camera_widget(pane, deliver, on_unavailable=None):
    """Hand ``deliver`` the pane's camera widget: at once if it exists, else
    on the GUI thread once the Camera Controls section is built (#1064).
    ``on_unavailable(error)`` runs instead should that section fail to
    build."""
    widget = pane.camera_control_widget

    if widget:
        deliver(widget)

        return

    GUI.invoke_later(pane.when_camera_controls_built, deliver, on_unavailable)


def answer_camera_unavailable(publisher, reply):
    """An ``on_unavailable`` that answers a waiting requester ``reply``,
    not ok, on ``publisher``."""

    def publish(error):
        publisher.publish(
            {**reply, "ok": False, "error": f"Device viewer camera: {error}"}
        )

    return publish
