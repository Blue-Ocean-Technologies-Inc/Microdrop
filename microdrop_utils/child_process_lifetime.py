# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Tie a spawned child process to this process's lifetime.

A child started with ``subprocess.Popen`` normally outlives a parent that
crashes or is killed outright. Pass ``parent_death_preexec_fn()`` as the
``preexec_fn`` and call ``kill_child_with_parent(process)`` right after the
spawn, and the child dies with the parent however the parent goes — kill -9
and TerminateProcess included.
"""

# Standard library imports.
import ctypes
import os
import signal
import sys

# Logger import.
from logger.logger_service import get_logger

logger = get_logger(__name__)

#: prctl option asking the kernel to signal the child when its parent dies.
PR_SET_PDEATHSIG = 1

#: Job limit flag: closing the job's last handle kills every process in it.
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000

#: SetInformationJobObject info class for JOBOBJECT_EXTENDED_LIMIT_INFORMATION.
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount", ctypes.c_uint64),
        ("WriteTransferCount", ctypes.c_uint64),
        ("OtherTransferCount", ctypes.c_uint64),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),
        ("PerJobUserTimeLimit", ctypes.c_int64),
        ("LimitFlags", ctypes.c_uint32),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_uint32),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_uint32),
        ("SchedulingClass", ctypes.c_uint32),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


def parent_death_preexec_fn():
    """Return a ``preexec_fn`` that makes the child die with this process.

    Linux only (``PR_SET_PDEATHSIG``); every other platform gets ``None``,
    which ``subprocess.Popen`` treats as no hook. The kernel ties the child
    to the spawning *thread*, so spawn from a thread that lives as long as
    the process — the main thread.
    """

    if not sys.platform.startswith("linux"):
        return None

    # Loaded here, before the fork: dlopen in the forked child of a
    # threaded parent can deadlock on the loader lock.
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    parent_pid = os.getpid()

    def die_with_parent():
        # Runs in the child between fork and exec, where logging is unsafe;
        # a failed prctl just leaves the child without the guarantee.
        libc.prctl(PR_SET_PDEATHSIG, signal.SIGTERM)

        # The parent may already have died between fork and prctl, in which
        # case the death signal will never come.
        if os.getppid() != parent_pid:
            os.kill(os.getpid(), signal.SIGTERM)

    return die_with_parent


def kill_child_with_parent(process):
    """Make the freshly spawned ``process`` die with this process.

    On Windows the child joins a kill-on-close job object; on Linux the
    ``preexec_fn`` from ``parent_death_preexec_fn`` already did the work.
    Failures are logged, never raised — the child still runs, it just may
    outlive a crash.
    """
    if sys.platform == "win32":
        _assign_to_kill_on_close_job(process)

    elif not sys.platform.startswith("linux"):
        logger.debug(
            f"child process {process.pid} is not tied to this process's "
            f"lifetime on {sys.platform}"
        )


def _assign_to_kill_on_close_job(process):
    """Put ``process`` in a job that is killed when this process exits."""
    # A private WinDLL so the argtypes set here never leak into other users
    # of the shared ctypes.windll.kernel32.
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, ctypes.c_wchar_p)
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = (
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_uint32,
    )
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.CloseHandle.argtypes = (ctypes.c_void_p,)
    kernel32.CloseHandle.restype = ctypes.c_int

    job = kernel32.CreateJobObjectW(None, None)

    if not job:
        logger.error(
            f"cannot create a job object for child process {process.pid}: "
            f"{ctypes.WinError(ctypes.get_last_error())}"
        )

        return

    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE

    limits_set = kernel32.SetInformationJobObject(
        job,
        JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )

    if not limits_set or not kernel32.AssignProcessToJobObject(
        job, int(process._handle)
    ):
        logger.error(
            f"cannot tie child process {process.pid} to this process's "
            f"lifetime: {ctypes.WinError(ctypes.get_last_error())}"
        )
        kernel32.CloseHandle(job)

        return

    # The kill fires when the job's last handle closes, which is when this
    # process exits, however it exits — so the handle stays open until then.
    process.kill_on_close_job_handle = job
    logger.debug(f"child process {process.pid} will die with this process")
