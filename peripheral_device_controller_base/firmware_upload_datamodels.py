"""Shared firmware-upload message contract for Pico-family peripherals.

Every board this covers takes the same upload options; only the topic (and
the safe default device id, applied frontend-side) differs per device, so the
payload model and its validated publisher live here once. Each device creates
one publisher bound to its own upload topic:

    upload_firmware_publisher = UploadFirmwarePublisher(
        topic=upload_firmware_topic(DEVICE_NAME))
"""

from pydantic import BaseModel, ConfigDict, Field

from microdrop_utils.dramatiq_pub_sub_helpers import ValidatedTopicPublisher


class UploadFirmwareData(BaseModel):
    """One firmware-upload run: mirrors firmware_uploader.upload_firmware.

    ``firmware_source`` is a folder tree OR a .zip bundle (the backend unzips
    a zip to a temp dir, uploads it, then deletes it). ``port`` empty means
    auto: the backend reuses a connected proxy's stored port, else probes for
    the board (whoami / Pico VID). ``device_id`` empty matches the first
    board that identifies at all (the frontend substitutes the device's own
    safe default before it gets here). ``upload_timeout_s`` 0 means never kill
    the upload.
    """
    model_config = ConfigDict(extra='forbid')

    firmware_source: str
    single_file: str = ""  # upload only this file (absolute or dir-relative)
    port: str = ""
    device_id: str = ""
    update_config: bool = False
    skip_filesystem_format: bool = False
    reset_after_upload: bool = True
    dry_run: bool = False
    upload_timeout_s: int = Field(default=0, ge=0)


class UploadFirmwarePublisher(ValidatedTopicPublisher):
    """Validated publisher for a device's upload_firmware topic.

    Exposes a keyword-only .publish(...) that mirrors the UploadFirmwareData
    fields for call-site readability.
    """
    validator_class = UploadFirmwareData

    def publish(self, *, firmware_source, single_file, port, device_id,
                update_config, skip_filesystem_format, reset_after_upload,
                dry_run, upload_timeout_s, **kw):
        super().publish({
            "firmware_source": firmware_source,
            "single_file": single_file,
            "port": port,
            "device_id": device_id,
            "update_config": update_config,
            "skip_filesystem_format": skip_filesystem_format,
            "reset_after_upload": reset_after_upload,
            "dry_run": dry_run,
            "upload_timeout_s": upload_timeout_s,
        }, **kw)
