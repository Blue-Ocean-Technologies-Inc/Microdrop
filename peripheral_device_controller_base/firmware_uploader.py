"""Qt-free firmware uploader for a MicroPython (Pico-family) peripheral board.

Shared by every Pico-based peripheral (heater, fluorescence, ...): the raw
per-board upload scripts were identical bar the default device id, so the
logic lives here once. Only the firmware SOURCE (a folder or a .zip bundle)
stays external (the request points at it). Files are pushed with mpremote,
one command per ``python -m mpremote`` subprocess: that keeps mpremote's
sys.argv/SystemExit machinery out of the backend process and lets each
command's output be captured for the caller's log.

Every function takes a ``log`` callable for progress lines (the firmware
upload service publishes them to the device's FIRMWARE_UPLOAD_LOG topic) and
``upload_firmware`` honours a ``cancel_event`` between steps — mid-command
cancellation is bounded by MPREMOTE_COMMAND_TIMEOUT_S.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

import serial
import serial.tools.list_ports

from microdrop_utils.hardware_device_monitoring_helpers import find_port_by_device_id

from logger.logger_service import get_logger
logger = get_logger(__name__)

#: Pico-family USB identity, shared by every board this uploader targets
#: (heater and fluorescence both enumerate as RP2040 VID:PID 2E8A:0005 at
#: 115200 baud). A board with a different HWID can override via the
#: ``hwids`` argument of ``upload_firmware``.
PICO_USB_VENDOR_ID = 0x2E8A
PICO_RP2040_HWID = "VID:PID=2E8A:0005"
BOARD_BAUDRATE = 115200

#: Hard ceiling per mpremote command so one wedged copy can't hang an upload
#: forever (the full-filesystem wipe is the slowest single command).
MPREMOTE_COMMAND_TIMEOUT_S = 120

#: The boot window is only open for ~3s after the board re-enumerates; the
#: Ctrl-C burst is bounded so a MISSED window doesn't keep firing Ctrl-C into
#: the now-running asyncio loop (which would wedge the board).
REPL_CATCH_BURST_S = 3.5
#: Startup-banner fragments proving the firmware is already running — the
#: boot window has passed, stop bursting immediately.
FIRMWARE_RUNNING_MARKERS = (
    b"System ready", b"USB listener started", b"Starting MicroPython",
    b"Command processor",
)


# ------------------------------------------------------------------ #
# mpremote plumbing                                                   #
# ------------------------------------------------------------------ #

def _run_mpremote_subprocess(cmd):
    """One ``python -m mpremote <cmd...>`` run with captured, merged output."""
    return subprocess.run(
        [sys.executable, "-m", "mpremote"] + cmd,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
        timeout=MPREMOTE_COMMAND_TIMEOUT_S,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def run_mpremote(cmd, log, retries=3):
    """Run a single mpremote command with retry, streaming its output through
    ``log``. Assumes the board is already at the REPL (see
    ensure_repl_via_window), so no per-command Ctrl-C is sent."""
    for attempt in range(1, retries + 1):
        try:
            completed = _run_mpremote_subprocess(cmd)
        except Exception as e:
            log(f"WARNING: mpremote attempt {attempt}/{retries} raised: {e}")
            time.sleep(0.5 * attempt)
            continue
        for line in completed.stdout.splitlines():
            if line.strip():
                log(f"  {line}")
        if completed.returncode == 0:
            return True
        log(f"WARNING: mpremote attempt {attempt}/{retries} failed "
            f"(exit {completed.returncode}): {' '.join(cmd)}")
        time.sleep(0.5 * attempt)
    log(f"ERROR: mpremote command failed after {retries} attempts: "
        f"{' '.join(cmd)}")
    return False


def _wipe_filesystem(port, log):
    """Wipe the board's filesystem contents WITHOUT touching the root itself.

    ``rm -rv :/`` removes every child but then tries to rmdir the root,
    which the board refuses (EPERM) — mpremote reports ``rm -r: cannot
    remove :/ Operation not permitted`` and exits non-zero on every retry
    even though the wipe actually happened (the standalone upload script
    had the same noise, its format step's result was just never checked).
    Removing each top-level entry instead ends clean.
    """
    try:
        listing = _run_mpremote_subprocess(["connect", port, "fs", "ls", ":/"])
    except Exception as e:
        listing = None
        logger.debug(f"Filesystem listing raised: {e}")
    if listing is None or listing.returncode != 0:
        log("WARNING: could not list the filesystem before the wipe; "
            "falling back to rm -r :/")
        run_mpremote(["connect", port, "rm", "-rv", ":/"], log)
        return
    # `fs ls :/` lines are "<size> <name>" (directories keep a trailing /),
    # preceded by an "ls :/" header — keep only the size-prefixed entries.
    entries = []
    for line in listing.stdout.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[0].isdigit():
            entries.append(parts[1].strip().rstrip("/"))
    if not entries:
        log("Filesystem already empty.")
        return
    for entry in entries:
        run_mpremote(["connect", port, "rm", "-rv", f":/{entry}"], log)


def _pull_device_config(port):
    """Best-effort single-attempt pull of the device's current config.json to
    a local temp file. Returns the temp Path on success, or None if the
    device has no config.json right now (a fresh board, or one already
    wiped) — that's an expected outcome, not an error, so no retries and no
    logging here; the caller decides what to report."""
    tmp_fd, tmp_name = tempfile.mkstemp(
        prefix="fluorescence_config_backup_", suffix=".json")
    os.close(tmp_fd)
    tmp_path = Path(tmp_name)
    try:
        completed = _run_mpremote_subprocess(
            ["connect", port, "cp", ":config.json", str(tmp_path)])
        pulled = completed.returncode == 0
    except Exception as e:
        logger.debug(f"config.json pull failed: {e}")
        pulled = False
    if not pulled or not tmp_path.exists() or tmp_path.stat().st_size == 0:
        tmp_path.unlink(missing_ok=True)
        return None
    return tmp_path


# ------------------------------------------------------------------ #
# Getting the board to a quiescent REPL                               #
# ------------------------------------------------------------------ #

def _current_pico_port(preferred):
    """The current Pico port, tolerating re-enumeration name changes."""
    devices = [p.device for p in serial.tools.list_ports.comports()]
    if preferred in devices:
        return preferred
    for p in serial.tools.list_ports.comports():
        if p.vid == PICO_USB_VENDOR_ID:
            return p.device
    return preferred


def _reset_and_catch_once(port, log, timeout_s):
    """One attempt: reboot a running firmware via '|||reset', then burst
    Ctrl-C to catch main.py's boot window. Returns (reached_repl, port)."""
    # Reboot a healthy running firmware into its boot window. Ctrl-C is NEVER
    # sent to the running loop (that can wedge it) — only during the window.
    try:
        with serial.Serial(port, BOARD_BAUDRATE, timeout=0) as ser:
            ser.write(b"\r|||reset\r\n")
            ser.flush()
    except Exception as e:
        log(f"WARNING: could not send |||reset (board may already be at "
            f"REPL): {e}")
    time.sleep(0.4)  # let the reset begin (USB drops) before the burst

    buf = b""
    ser = None
    t0 = time.time()
    reopened_at = None
    cur = port
    while time.time() - t0 < timeout_s:
        if ser is None:
            cur = _current_pico_port(port)
            try:
                ser = serial.Serial(cur, BOARD_BAUDRATE, timeout=0)
            except Exception:
                time.sleep(0.02)
                continue
            if reopened_at is None:
                reopened_at = time.time()
        # Stop bursting once we've hammered the live port past the window, or
        # if the firmware is clearly already running — never overrun into the
        # loop.
        if reopened_at is not None and time.time() - reopened_at > REPL_CATCH_BURST_S:
            break
        if any(marker in buf for marker in FIRMWARE_RUNNING_MARKERS):
            break
        try:
            ser.write(b"\x03")
            buf += ser.read(256)
        except Exception:
            try:
                ser.close()
            except Exception:
                pass
            ser = None
            reopened_at = None
            continue
        if b">>>" in buf or b"staying at REPL" in buf:
            try:
                ser.close()
            except Exception:
                pass
            return True, cur
        time.sleep(0.02)
    if ser is not None:
        try:
            ser.close()
        except Exception:
            pass
    return False, cur


def ensure_repl_via_window(port, log, attempts=4, timeout_s=7):
    """Get the board to a quiescent REPL WITHOUT a UF2 reflash or physical
    replug. Reboots a running firmware via its own '|||reset' command and
    catches main.py's boot-time safe-mode window with a Ctrl-C burst.
    Catching a short window across USB re-enumeration is timing-sensitive, so
    each miss simply reboots and tries again. Returns (port, reached_repl)
    with the possibly re-enumerated port name."""
    cur = port
    for attempt in range(1, attempts + 1):
        ok, cur = _reset_and_catch_once(cur, log, timeout_s)
        if ok:
            log(f"Reached REPL via boot window on {cur} (attempt {attempt})")
            return cur, True
        log(f"WARNING: boot-window catch attempt {attempt}/{attempts} "
            f"missed; retrying")
    return cur, False


# ------------------------------------------------------------------ #
# config.json diffing                                                 #
# ------------------------------------------------------------------ #

def _flatten_json(d, prefix=""):
    """Flatten a nested dict into {"a.b.c": leaf_value} pairs. Lists and
    other non-dict values are treated as leaves (compared by equality),
    which is sufficient for config.json's shape (nested objects with the
    occasional flat sensor-name list)."""
    out = {}
    if isinstance(d, dict):
        for k, v in d.items():
            out.update(_flatten_json(v, f"{prefix}.{k}" if prefix else str(k)))
    else:
        out[prefix] = d
    return out


def _diff_configs(device_config_path, repo_config_path, log):
    """Log a read-only, key-by-key diff between the device's current
    config.json and the repo's copy. Purely informational — this never
    merges or resolves anything; telling a stale placeholder apart from an
    intentional per-board tuning value isn't something code can safely
    judge, so that call is always left to the human running this."""
    try:
        device_cfg = json.loads(Path(device_config_path).read_text())
    except Exception as e:
        log(f"WARNING: could not parse device's config.json for diff: {e}")
        return
    try:
        repo_cfg = json.loads(Path(repo_config_path).read_text())
    except Exception as e:
        log(f"WARNING: could not parse repo config.json for diff: {e}")
        return

    device_flat = _flatten_json(device_cfg)
    repo_flat = _flatten_json(repo_cfg)
    keys = sorted(set(device_flat) | set(repo_flat))
    diffs = [(k, device_flat.get(k, "<missing>"), repo_flat.get(k, "<missing>"))
             for k in keys]
    diffs = [d for d in diffs if d[1] != d[2]]

    if not diffs:
        log("config.json: device matches repo (no differences)")
        return
    log(f"config.json: device and repo differ in {len(diffs)} key(s):")
    for k, device_value, repo_value in diffs:
        log(f"    {k}: device={device_value!r}  repo={repo_value!r}")


# ------------------------------------------------------------------ #
# File selection                                                      #
# ------------------------------------------------------------------ #

#: Packaging junk that a zip may carry but must never reach the board: macOS
#: Finder adds a top-level __MACOSX/ tree of ._* AppleDouble sidecar files
#: when zipping a folder.
_ARCHIVE_JUNK_DIRS = frozenset({"__pycache__", "__MACOSX"})


def _keep(f: Path) -> bool:
    """True if f is a candidate for upload at all (before the config.json
    filter): no bytecode caches, packaging junk, markdown, hidden files/dirs,
    or suffix-less non-directories."""
    if _ARCHIVE_JUNK_DIRS.intersection(f.parts):
        return False
    if f.suffix == ".pyc":
        return False
    if f.suffix == ".md":
        return False
    if any(part.startswith(".") for part in f.parts):
        return False
    if not f.is_dir() and f.suffix == "":
        return False
    return True


def _is_top_level_config(f: Path, fw_path: Path) -> bool:
    return f.name == "config.json" and f.parent == fw_path


def _cancelled(cancel_event, log):
    if cancel_event is not None and cancel_event.is_set():
        log("Upload cancelled.")
        return True
    return False


# ------------------------------------------------------------------ #
# Zip bundle handling                                                 #
# ------------------------------------------------------------------ #

def _firmware_root(extracted_dir: Path) -> Path:
    """The firmware root inside an extracted bundle. Packaging junk (macOS
    __MACOSX/, hidden dot-entries) is ignored; if exactly one real directory
    remains at the top level (a zip of the firmware folder), that directory
    is the root, otherwise the extraction dir is.

    Ignoring the junk matters: a Finder-made zip carries both ``firmware/``
    and ``__MACOSX/`` at the top level, and without this the wrapper wouldn't
    be unwrapped — every file would land under ``:firmware/`` on the board."""
    entries = [e for e in extracted_dir.iterdir()
               if e.name not in _ARCHIVE_JUNK_DIRS
               and not e.name.startswith(".")]
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extracted_dir


def _extract_firmware_zip(zip_path: Path, log):
    """Unzip a firmware bundle into a fresh temp dir and return
    ``(firmware_root, temp_dir)``. ``temp_dir`` is always the mkdtemp root so
    the caller deletes exactly what was created, even when the firmware root
    is a subdirectory of it."""
    temp_dir = Path(tempfile.mkdtemp(prefix="microdrop_fw_"))
    log(f"Unzipping firmware bundle {zip_path.name} -> {temp_dir}")
    with zipfile.ZipFile(zip_path) as archive:
        names = archive.namelist()
        archive.extractall(temp_dir)
    for name in names:
        logger.debug(f"  extracted: {name}")
    log(f"Unzipped {len(names)} entr{'y' if len(names) == 1 else 'ies'}.")
    root = _firmware_root(temp_dir)
    if root != temp_dir:
        log(f"Firmware root inside the bundle: {root.name}/")
    return root, temp_dir


def _cleanup_extracted_dir(temp_dir: Path, log):
    """Delete the temp dir an upload's zip bundle was extracted into."""
    log(f"Deleting unzipped firmware copy {temp_dir}")
    try:
        shutil.rmtree(temp_dir)
    except Exception as e:
        logger.warning(f"Could not delete temp firmware dir {temp_dir}: {e}")
        log(f"WARNING: could not delete unzipped copy {temp_dir}: {e}")


# ------------------------------------------------------------------ #
# Main entry point                                                    #
# ------------------------------------------------------------------ #

def upload_firmware(
    firmware_path,
    port=None,
    reset_device=True,
    single_file=None,
    no_format=False,
    update_config=False,
    device_id=None,
    dry_run=False,
    hwids=None,
    log=logger.info,
    cancel_event=None,
):
    """Upload the firmware tree (or one file) to the board. Returns success.

    Args:
        firmware_path: Directory containing the firmware files, OR a .zip
            bundle of them — a zip is extracted to a temp dir, uploaded, and
            the temp dir deleted before returning.
        port: Serial port to use; None probes for the board by HWID and
            whoami ``device_id`` (find_port_by_device_id — an empty/None
            device_id claims the first board that identifies at all).
        hwids: USB HWIDs to probe when ``port`` is None; defaults to the
            Pico RP2040 id shared by every board this uploader targets.
        reset_device: Reset the device after a fully successful upload.
        single_file: Upload only this file (absolute, or relative to
            firmware_path).
        no_format: Skip formatting the filesystem first.
        update_config: If True, wipe everything including config.json and
            push the repo's copy (no backup kept). If False (default), the
            device's current config.json is backed up before the wipe and
            restored afterward, so per-board tuned values survive a routine
            full reflash. Either way a key-by-key diff between the device's
            and repo's config.json is logged before anything is touched.
            Ignored when single_file is set.
        dry_run: Log what would happen and return without touching the
            device.
        log: Callable receiving one progress line per call.
        cancel_event: threading.Event checked between steps; setting it
            aborts the upload (bounded by MPREMOTE_COMMAND_TIMEOUT_S while a
            command is in flight).
    """
    fw_path = Path(firmware_path)
    temp_extract_dir = None
    try:
        # Zip bundle: unzip to a temp dir, upload that, delete it in finally.
        if fw_path.is_file() and fw_path.suffix.lower() == ".zip":
            fw_path, temp_extract_dir = _extract_firmware_zip(fw_path, log)

        if single_file:
            single_file_path = Path(single_file)
            if single_file_path.is_absolute():
                files = [single_file_path]
                fw_path = single_file_path.parent
            else:
                files = [fw_path / single_file_path]
            if not files[0].exists():
                log(f"ERROR: single file {single_file} does not exist")
                return False
            skipped_config = False
        else:
            if not fw_path.is_dir():
                log(f"ERROR: firmware path {firmware_path} is not a directory")
                return False
            files = [f for f in fw_path.glob("**/*") if _keep(f)]
            skipped_config = False
            if not update_config:
                before = len(files)
                files = [f for f in files
                         if not _is_top_level_config(f, fw_path)]
                skipped_config = len(files) < before
            # boot.py first, then main.py, then everything else.
            files.sort(key=lambda f: (0 if f.name == "boot.py" else
                                      (1 if f.name == "main.py" else 2)))

        if not files:
            log("WARNING: no files found to upload")
            return False

        will_format = not single_file and not no_format
        need_restore = will_format and not update_config and not single_file

        if dry_run:
            log(f"[dry-run] Firmware source: {fw_path}")
            log(f"[dry-run] Format filesystem: {will_format}")
            if update_config:
                log("[dry-run] config.json: OVERWRITE with repo version "
                    "(update_config)")
            elif need_restore:
                log("[dry-run] config.json: back up device's current copy "
                    "before the wipe, then restore it afterward (default — "
                    "device keeps its own config). If the device has no "
                    "config.json to back up, the repo's copy is pushed "
                    "instead of leaving the device with none.")
            else:
                log("[dry-run] config.json: left untouched (no format, no "
                    "wipe happening)")
            if not single_file:
                log("[dry-run] config.json diff vs repo: only shown on a "
                    "real run (requires reading the device)")
            for f in files:
                tag = "mkdir" if f.is_dir() else "upload"
                log(f"[dry-run]   [{tag}] {f.relative_to(fw_path).as_posix()}")
            if skipped_config:
                log("[dry-run]   [skip: config] config.json (enable "
                    "update_config to overwrite it)")
            return True

        if not port:
            try:
                port = find_port_by_device_id(hwids or [PICO_RP2040_HWID],
                                              device_id or "")
            except Exception as e:
                log(f"ERROR: {e}")
                return False
        log(f"Using port: {port}")

        if _cancelled(cancel_event, log):
            return False

        # Get the board to a quiescent REPL first. Do this ONCE; all the
        # mpremote ops below then run against an idle REPL. The port name can
        # change after the reset's USB re-enumeration, so adopt whatever
        # ensure_repl_via_window reports back. If the REPL can't be
        # confirmed, ABORT rather than let mpremote hammer Ctrl-C at a
        # running loop (which would wedge the board).
        port, at_repl = ensure_repl_via_window(port, log)
        if not at_repl:
            log("ERROR: could not drop the board to its REPL. It may be "
                "fully wedged. Power-cycle it and run recover_pico.py, then "
                "retry.")
            return False

        if _cancelled(cancel_event, log):
            return False

        # Read the device's current config.json (best-effort) before doing
        # anything destructive: drives both the diff-vs-repo report and, when
        # not update_config, gives us something to restore after a full wipe.
        device_config_backup = None
        if not single_file:
            pulled = _pull_device_config(port)
            repo_config_path = fw_path / "config.json"
            if pulled is not None:
                if repo_config_path.exists():
                    _diff_configs(pulled, repo_config_path, log)
                if need_restore:
                    log("config.json: will be backed up and restored after "
                        "the reflash (device keeps its own copy)")
                    device_config_backup = pulled
                else:
                    if update_config:
                        log("config.json: overwriting with repo version "
                            "(update_config); see diff above for what "
                            "changes")
                    pulled.unlink(missing_ok=True)
            else:
                log("config.json: device currently has none (fresh board, or "
                    "previously wiped) — nothing to diff or back up")
                if need_restore:
                    if repo_config_path.exists():
                        log("WARNING: config.json: nothing on the device to "
                            "back up, so pushing the repo's copy instead of "
                            "leaving the device with none after the wipe. "
                            "Enable update_config to do this intentionally "
                            "and skip this warning.")
                        files.append(repo_config_path)
                    else:
                        log("WARNING: filesystem will be formatted and there "
                            "is no existing config.json to restore, and the "
                            "repo has no config.json either — the device "
                            "will have NO config.json until you add one "
                            "manually.")

        if will_format:
            if _cancelled(cancel_event, log):
                if device_config_backup is not None:
                    device_config_backup.unlink(missing_ok=True)
                return False
            log("Formatting device filesystem...")
            _wipe_filesystem(port, log)
        elif no_format:
            log("Skipping filesystem format")

        all_successful = True
        for i, filename in enumerate(files):
            if _cancelled(cancel_event, log):
                all_successful = False
                break
            log(f"Uploading file {i + 1}/{len(files)}: {filename}")

            local_path = str(filename.absolute())
            # The device's filesystem always uses forward slashes, regardless
            # of the host OS. str(Path) would use "\" on Windows, which the
            # Pico treats as a literal filename character rather than a
            # directory separator — nested files would land flat on the
            # device instead of inside their subdirectory.
            remote_path = filename.relative_to(fw_path).as_posix()

            if filename.is_dir():
                # Best-effort: mkdir fails when the dir already exists (e.g.
                # on no-format re-uploads), which is fine — don't abort on it.
                run_mpremote(["connect", port, "mkdir", remote_path],
                             log, retries=1)
                continue

            if run_mpremote(["connect", port, "cp", local_path,
                             f":{remote_path}"], log):
                log(f"Successfully uploaded {filename}")
            else:
                log(f"ERROR: failed to upload {filename} after retries")
                all_successful = False
                break

        # Restore the device's original config.json if we backed one up. This
        # runs regardless of all_successful — the wipe already happened, so
        # leaving the device without its config would be strictly worse than
        # a partial upload.
        if device_config_backup is not None:
            log("Restoring device's original config.json...")
            if run_mpremote(["connect", port, "cp",
                             str(device_config_backup), ":config.json"], log):
                log("config.json restored.")
            else:
                log("ERROR: failed to restore config.json backup after "
                    "wipe! Device has NO config.json now.")
                all_successful = False
            device_config_backup.unlink(missing_ok=True)

        if reset_device and all_successful:
            log("Resetting device...")
            run_mpremote(["connect", port, "reset"], log, retries=1)

        return all_successful

    except Exception as e:
        logger.exception("Error during firmware upload")
        log(f"ERROR: error during firmware upload: {e}")
        return False
    finally:
        if temp_extract_dir is not None:
            _cleanup_extracted_dir(temp_extract_dir, log)
