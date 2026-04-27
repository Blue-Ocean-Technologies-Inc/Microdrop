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