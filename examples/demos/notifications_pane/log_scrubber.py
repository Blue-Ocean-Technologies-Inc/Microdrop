# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

"""Scrub machine- and person-specific text out of log records before they
are stored as public demo samples. Qt-free.

Paths become repo-relative (``src/…``, ``<env>/Lib/…``) or neutral
(``<home>/…``, ``<experiment>``); experiment timestamps, e-mail
addresses, user@host pairs, IP addresses and device serial numbers are
replaced. The public USB VID:PID pairs the source names are kept.
"""

# Standard library imports.
import re

#: (pattern, replacement), applied in order: specific paths before general.
SCRUB_RULES = (
    # The checkout and its pixi environment.
    (
        re.compile(
            r"[A-Za-z]:[\\/][^\s\"']*?[\\/]\.pixi[\\/]envs[\\/][^\\/\s\"']+[\\/]"
        ),
        "<env>/",
    ),
    (
        re.compile(r"[A-Za-z]:[\\/][^\s\"']*?[\\/]microdrop-py[\\/]src[\\/]"),
        "src/",
    ),
    # Experiment folders, wherever they are.
    (
        re.compile(
            r"[A-Za-z]:[\\/][^\s\"']*?[\\/]Experiments[\\/]\d{4}_\d{2}_\d{2}-[\d_]+"
        ),
        "<experiment>",
    ),
    # Any other home folder, on Windows or POSIX.
    (re.compile(r"[A-Za-z]:[\\/]Users[\\/][^\\/\s\"']+"), "<home>"),
    (re.compile(r"/(?:home|Users)/[^/\s\"']+"), "<home>"),
    # Timestamps MicroDrop names experiments and messages with, also when
    # a repr cut off their start ("ti...6_08_05-16_01_58_191000").
    (re.compile(r"\d{1,4}_\d{2}_\d{2}-\d{2}_\d{2}_\d{2}(?:_\d+)?"), "<timestamp>"),
    # People and machines.
    (re.compile(r"\b[\w.+-]+@[\w-]+(?:\.[\w-]+)*\b"), "<user@host>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<ip>"),
    (re.compile(r"\bAzureAD[\\/]\w+", re.IGNORECASE), "<user>"),
    # Serial numbers after a VID:PID or in a USB instance path.
    (re.compile(r"(VID[:_]PID=[0-9A-Fa-f]{4}:[0-9A-Fa-f]{4})\s+SER=\w+"), r"\1"),
    (re.compile(r"(VID_[0-9A-Fa-f]{4}&PID_[0-9A-Fa-f]{4})\\\w+"), r"\1"),
    (
        re.compile(r"\b(serial(?: number)?[:= ]+)[\w-]{6,}", re.IGNORECASE),
        r"\1<serial>",
    ),
)


def scrub_log_text(text):
    """``text`` with paths, names, addresses and serials made neutral;
    backslashes in scrubbed paths become forward slashes."""

    for pattern, replacement in SCRUB_RULES:
        text = pattern.sub(replacement, text)

    # The rest of a scrubbed path, e.g. "src/device_viewer\models\x.py".
    return re.sub(
        r"(src/|<env>/|<home>|<experiment>)([^\s\"']*)",
        lambda match: match[1] + match[2].replace("\\", "/"),
        text,
    )
