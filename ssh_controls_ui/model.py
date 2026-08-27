# (C) Copyright 2024-2026 Blue Ocean Technologies, Inc., Toronto, ON
# All rights reserved.
#
# This software is provided without warranty under the terms of the AGPL-3.0
# license included in LICENSE and may be redistributed only under the
# conditions described in the aforementioned license. The license is also
# available online at https://www.gnu.org/licenses/agpl-3.0.txt
#
# Thanks for using Microdrop open source!

from traits.api import HasTraits, Str, Password, Int


class SSHControlModel(HasTraits):
    """Transient per-session state for the SSH Key Portal dialog.

    Persisted fields (host, port, username, key_name) live on
    ``SSHControlPreferences`` — see ``preferences.py``. Password is
    intentionally session-only: it is used once for the key upload,
    and plaintext ETSConfig persistence is a security risk.
    """
    host = Str
    port = Int
    username = Str
    password = Password
    generated_pub_key = Str
    generated_pub_key_path = Str
    key_name = Str