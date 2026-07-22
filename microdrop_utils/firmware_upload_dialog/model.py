"""Qt-free model for the shared firmware-upload dialog: the request options,
the live log text, and the payload builder for the validated publisher.

Device-specific values (the firmware-dir default and the safe fallback device
id) are injected as traits by the controller, so the model itself carries no
per-device knowledge.
"""

from pathlib import Path

import serial.tools.list_ports

from traits.api import (
    Bool, Button, Directory, File, HasTraits, Range, Str, observe,
    List,
)

from .consts import (
    DEVICE_ID_PLACEHOLDER, PICO_USB_VENDOR_ID, PORT_ENTRY_SEPARATOR,
)


class FirmwareUploadModel(HasTraits):
    """Options for one firmware-upload request, plus the live log."""

    #: Injected by the controller (device-specific).
    default_firmware_dir = Str()
    #: Safe id the upload targets when no whoami id is known (device-specific).
    default_device_id = Str()

    #: Firmware source: a folder tree OR a .zip bundle (the backend unzips a
    #: zip to a temp dir, uploads it, then deletes it). Kept a Directory trait
    #: for the native folder-browse; the zip-browse button writes a .zip path
    #: into the same field.
    firmware_source = Directory()
    browse_firmware_zip = Button()
    single_file = File()

    #: True: the backend resolves the port (a connected proxy's stored port,
    #: else whoami / VID probing). False: send the selection below.
    auto_port = Bool(True)
    available_ports = List(Str)
    selected_port_entry = Str()
    refresh_ports = Button()

    #: The connected board's whoami device_id, mirrored from live_state by the
    #: controller and shown read-only. Shows DEVICE_ID_PLACEHOLDER until a
    #: whoami arrives, so a real id here proves the signal was received. When
    #: no id is known the upload still targets default_device_id (see
    #: upload_request_kwargs) so an empty match can't grab a sibling board on
    #: the shared VID:PID.
    device_id = Str(DEVICE_ID_PLACEHOLDER)

    update_config = Bool(False)
    skip_filesystem_format = Bool(False)
    reset_after_upload = Bool(True)
    dry_run = Bool(False)

    #: Kill the upload if it runs longer than this many seconds (0 = never);
    #: enforced by the backend service, sent along in the request.
    upload_timeout_s = Range(0, 10000, 0)

    uploading = Bool(False)
    upload_log = Str()
    clear_log = Button()

    # Section collapse states (fluo controls pane pattern: an arrow-glyph
    # header toggles each `show_*`, the bordered group is visible_when it).
    show_source = Bool(True)
    show_port = Bool(True)
    show_options = Bool(True)

    def _firmware_source_default(self):
        return self.default_firmware_dir

    def _available_ports_default(self):
        return self._scan_port_entries()

    def _selected_port_entry_default(self):
        return self.available_ports[0] if self.available_ports else ""

    @staticmethod
    def _scan_port_entries():
        """Dropdown entries for every serial port, Pico-vendor ports first."""
        ports = sorted(
            serial.tools.list_ports.comports(),
            key=lambda p: (p.vid != PICO_USB_VENDOR_ID, str(p.device)),
        )
        return [f"{p.device}{PORT_ENTRY_SEPARATOR}{p.description}"
                for p in ports]

    @observe("refresh_ports")
    def _on_refresh_ports(self, event):
        entries = self._scan_port_entries()
        self.available_ports = entries
        if self.selected_port_entry not in entries:
            self.selected_port_entry = entries[0] if entries else ""
        listing = "\n".join(f"    {entry}" for entry in entries) or "    (none)"
        self.upload_log += f"Found {len(entries)} serial port(s):\n{listing}\n"

    @observe("clear_log")
    def _on_clear_log(self, event):
        self.upload_log = ""

    def selected_port_device(self):
        return self.selected_port_entry.split(PORT_ENTRY_SEPARATOR)[0]

    def _entry_for_device(self, port_device):
        """The dropdown entry whose port device matches, or None."""
        for entry in self.available_ports:
            if entry.split(PORT_ENTRY_SEPARATOR)[0] == port_device:
                return entry
        return None

    def sync_selected_port(self, port_device):
        """Point the combo at the connected / auto-detected port, rescanning
        the port list if it isn't currently listed. No-op if the port can't
        be matched (e.g. empty, or disconnected)."""
        if not port_device:
            return
        entry = self._entry_for_device(port_device)
        if entry is None:
            self.available_ports = self._scan_port_entries()
            entry = self._entry_for_device(port_device)
        if entry is not None:
            self.selected_port_entry = entry

    def _effective_device_id(self):
        """The id to flash: the board's real whoami id when known, else the
        device's default — never the placeholder, since an empty / "-" match
        could grab a sibling board on the shared VID:PID."""
        if self.device_id and self.device_id != DEVICE_ID_PLACEHOLDER:
            return self.device_id
        return self.default_device_id

    def _firmware_source_is_zip(self):
        return self.firmware_source.lower().endswith(".zip")

    def validation_problems(self):
        """Human-readable reasons the upload can't start (empty when OK)."""
        problems = []
        if self.single_file:
            if not Path(self.single_file).is_file():
                problems.append(f"Single file not found: {self.single_file}")
        elif self._firmware_source_is_zip():
            if not Path(self.firmware_source).is_file():
                problems.append(
                    f"Firmware zip not found: {self.firmware_source}")
        elif not Path(self.firmware_source).is_dir():
            problems.append(
                f"Firmware folder not found: {self.firmware_source}")
        if not self.auto_port and not self.selected_port_entry:
            problems.append("Manual port mode is on but no port is selected.")
        return problems

    def upload_request_kwargs(self):
        """Keyword payload for the upload publisher reflecting the current
        options (empty port = backend auto-resolution)."""
        return dict(
            firmware_source=self.firmware_source,
            single_file=self.single_file,
            port="" if self.auto_port else self.selected_port_device(),
            device_id=self._effective_device_id(),
            update_config=self.update_config,
            skip_filesystem_format=self.skip_filesystem_format,
            reset_after_upload=self.reset_after_upload,
            dry_run=self.dry_run,
            upload_timeout_s=self.upload_timeout_s,
        )
