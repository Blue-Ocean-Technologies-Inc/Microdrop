# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

# (C) Copyright 2026-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Drive portable DropBots from this machine: GUI and Redis here, backends on the Pis.

Each Pi runs on a mirror of this checkout (its commit plus uncommitted edits)
in a side worktree, so whatever branch its own checkout is on stays untouched.
An SSH reverse tunnel per Pi maps its Redis port onto this machine's, so no
``redis_settings.json`` changes and no firewall rule is needed: every Pi
connects to "its" local Redis and lands on the one the GUI owns.

The pub/sub router gives every process its own listener queue, so a request
from this GUI reaches every Pi's backend and all the boards act together.
Their signals come back on the same topics, so the status this GUI shows is
whichever board spoke last — demo boards should be set up alike.

Stop the Microdrop app on each Pi first — it holds the board's serial port and
its own Redis on the tunnel's port. Then, from ``microdrop-py/src``::

    pixi run python -m examples.demos.remote_portables [--mirror] [HOST ...]

``--mirror`` runs the full app on each Pi's own screen instead of the bare
backend: every GUI follows the boards (status, capacitance, alarms, protocol
runs), and each Pi's Preferences govern its backend. Hand-clicked electrodes
and protocol-tree edits stay local to the GUI they were made in, so drive from
this GUI and watch on the others.

Closing this GUI sends a Ctrl+C through each Pi's terminal, so every backend
shuts its board down cleanly. Host-bound pieces stay on each Pi: cameras have
no stream here, and files a backend saves land in its Pi's experiment folders.
"""

# Standard library imports.
import argparse
import os
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

# Microdrop utils imports.
from microdrop_utils.broker_server_helpers import (
    REDIS_HOST,
    REDIS_PORT,
    is_redis_running,
)
from microdrop_utils.source_update_startup import SKIP_GIT_UPDATE_ENV_VAR

DEFAULT_HOST = "portable-dropbot-user@dropbot"
DEFAULT_IDENTITY = Path.home() / ".ssh" / "id_rsa_portable_dropbot_1"

#: Each Pi's launcher checkout; the demo worktree sits beside its ``src``.
REMOTE_LAUNCHER = "~/Desktop/pixi-microdrop/microdrop-py"
REMOTE_WORKTREE = "src-remote-demo"

REDIS_START_TIMEOUT_S = 60
STOP_TIMEOUT_S = 10
CTRL_C = b"\x03"
SRC = Path(__file__).resolve().parents[2]


def git(*args):
    """Run git in this checkout and return its raw output."""
    return subprocess.run(
        ["git", *args], cwd=SRC, check=True, capture_output=True
    ).stdout


def ssh_command(args, host, remote_command, *options):
    """Build an ssh invocation of ``remote_command`` on ``host``."""
    command = ["ssh", "-o", "ConnectTimeout=10", *options]

    if args.identity.exists():
        command += ["-i", str(args.identity)]

    return [*command, host, remote_command]


def sync_remote_worktrees(args):
    """Mirror this checkout onto every Pi's demo worktree: HEAD plus local edits.

    Untracked files are not carried over — commit or ``git add -N`` them.
    """
    commit = git("rev-parse", "HEAD").decode().strip()
    patch = git("diff", "--binary", "HEAD")

    script = (
        f"set -e; cd {REMOTE_LAUNCHER}/src; "
        f"git cat-file -e {commit}^{{commit}} 2>/dev/null || git fetch -q origin; "
        f"[ -d ../{REMOTE_WORKTREE} ] || "
        f"git worktree add -q --detach ../{REMOTE_WORKTREE} {commit}; "
        f"cd ../{REMOTE_WORKTREE}; git reset -q --hard {commit}; "
        f"{'git apply --whitespace=nowarn' if patch else 'true'}"
    )

    for host in args.hosts:
        print(f"Mirroring {commit[:9]} (+{len(patch)} bytes of edits) on {host}...")
        result = subprocess.run(ssh_command(args, host, script), input=patch)

        if result.returncode:
            sys.exit(f"Could not mirror {commit[:9]} on {host} — is it pushed?")


def start_frontend():
    """Start the portable GUI here; it owns the Redis server every Pi uses."""
    return subprocess.Popen(
        [
            sys.executable,
            "-m",
            "examples.run_device_viewer_pluggable",
            "--device",
            "portable",
            "--plugins",
            "frontend",
        ],
        cwd=SRC,
        # Every side runs the commit it was given: no release switch mid-demo.
        env={**os.environ, SKIP_GIT_UPDATE_ENV_VAR: "1"},
    )


def wait_for_redis(frontend):
    """Block until the GUI's Redis accepts connections."""
    deadline = time.monotonic() + REDIS_START_TIMEOUT_S

    while not is_redis_running():
        if frontend.poll() is not None:
            sys.exit("The GUI stopped before its Redis server came up.")

        if time.monotonic() > deadline:
            frontend.terminate()
            sys.exit(f"No Redis on {REDIS_HOST}:{REDIS_PORT} after the GUI started.")

        time.sleep(0.2)


def remote_app_command(mirror):
    """Return a Pi's half: the headless backend, or the full app on its screen.

    The full app finds the tunnelled Redis already listening, so it starts no
    server of its own and joins the GUI's.
    """
    if mirror:
        plugins = "frontend backend"
        qt_env = "DISPLAY=:0 XDG_RUNTIME_DIR=/run/user/1000"

    else:
        plugins = "backend"
        qt_env = "QT_QPA_PLATFORM=offscreen"

    return (
        f"cd {REMOTE_LAUNCHER}/{REMOTE_WORKTREE} && "
        f"{SKIP_GIT_UPDATE_ENV_VAR}=1 {qt_env} "
        "exec ~/.pixi/bin/pixi run --manifest-path ../pyproject.toml python -m "
        f"examples.run_device_viewer_pluggable --device portable --plugins {plugins}"
    )


def start_remote_app(args, host):
    """Start a Pi's half over ssh, its Redis port tunnelled back here."""
    # -tt gives the Pi's app a terminal we can Ctrl+C through; ssh exits when
    # the Pi's own Redis holds the port or the link drops for 15 s.
    command = ssh_command(
        args,
        host,
        remote_app_command(args.mirror),
        "-tt",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=5",
        "-o",
        "ServerAliveCountMax=3",
        "-R",
        f"{REDIS_PORT}:{REDIS_HOST}:{REDIS_PORT}",
    )

    # Its own process group keeps a console Ctrl+C away from ssh, so the
    # Pi's app is always stopped through its terminal, never by a hangup.
    process = subprocess.Popen(
        command,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
    )

    threading.Thread(target=echo_output, args=(host, process), daemon=True).start()

    return process


def echo_output(host, process):
    """Print a Pi's console output, each line tagged with its host."""
    for line in process.stdout:
        text = line.decode(errors="replace").rstrip()

        if text:
            print(f"[{host}] {text}", flush=True)


def stop_remote_apps(processes):
    """Ctrl+C every Pi's app at once, so each shuts its board down cleanly."""
    running = [process for process in processes if process.poll() is None]

    for process in running:
        try:
            process.stdin.write(CTRL_C)
            process.stdin.flush()

        except OSError:
            # Its ssh is already closing; the wait below settles it.
            pass

    deadline = time.monotonic() + STOP_TIMEOUT_S

    for process in running:
        try:
            process.wait(timeout=max(0.0, deadline - time.monotonic()))

        except subprocess.TimeoutExpired:
            process.terminate()
            process.wait()


@contextmanager
def remote_apps(args):
    """Run every Pi's half for the duration of the block."""
    processes = {host: start_remote_app(args, host) for host in args.hosts}

    try:
        yield processes

    finally:
        stop_remote_apps(processes.values())


def watch(frontend, remotes):
    """Wait out the GUI, saying once for each Pi whose app goes away first."""
    reported = set()

    while frontend.poll() is None:
        for host, process in remotes.items():
            if host not in reported and process.poll() is not None:
                print(
                    f"\n{host}'s app stopped (ssh exit {process.returncode}) — "
                    "this GUI no longer drives its board."
                )
                reported.add(host)

        time.sleep(0.5)


def main():
    """Sync the Pis, start the GUI, then each Pi's half for the GUI's lifetime."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "hosts",
        nargs="*",
        default=[DEFAULT_HOST],
        help=f"ssh destinations of the Pis (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--identity",
        type=Path,
        default=DEFAULT_IDENTITY,
        help="ssh key, used when the file exists",
    )
    parser.add_argument(
        "--mirror",
        action="store_true",
        help="also show the GUI on each Pi's screen, following the boards",
    )
    args = parser.parse_args()

    sync_remote_worktrees(args)

    frontend = start_frontend()

    try:
        wait_for_redis(frontend)

        with remote_apps(args) as remotes:
            watch(frontend, remotes)

    finally:
        # A console Ctrl+C reaches the GUI too; let it save its layout first.
        try:
            frontend.wait(timeout=STOP_TIMEOUT_S)

        except subprocess.TimeoutExpired:
            frontend.terminate()


if __name__ == "__main__":
    main()
