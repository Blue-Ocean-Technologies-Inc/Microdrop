import os
import unittest
from unittest.mock import patch

from ssh_controls_ui.preferences import (
    SSHControlPreferences,
    SSHControlPreferencesPane,
    _sanitize_host,
)

class TestSSHControlPreferences(unittest.TestCase):
    def test_sanitize_host(self):
        self.assertEqual(_sanitize_host("192.168.1.10"), "192_168_1_10")
        self.assertEqual(_sanitize_host("my-host.local"), "my-host_local")
        self.assertEqual(_sanitize_host("::1"), "__1")
        self.assertEqual(_sanitize_host(""), "")

    @patch.dict(os.environ, {
        "REMOTE_HOST_IP_ADDRESS": "10.0.0.1",
        "REMOTE_HOST_USERNAME": "testuser",
        "REMOTE_SSH_PORT": "2222"
    })
    def test_preferences_defaults(self):
        # We need to clear any persisted preferences for this test to be reliable
        # but since we're in a test env, hopefully it's clean.
        prefs = SSHControlPreferences()
        
        # Check defaults from env
        self.assertEqual(prefs.host, "10.0.0.1")
        self.assertEqual(prefs.username, "testuser")
        self.assertEqual(prefs.port, 2222)
        
        # Check auto-derived device_id
        self.assertEqual(prefs.device_id, "10_0_0_1")

    def test_auto_derive_device_id(self):
        prefs = SSHControlPreferences(host="1.2.3.4")
        self.assertEqual(prefs.device_id, "1_2_3_4")
        
        # Change host, device_id should follow
        prefs.host = "5.6.7.8"
        self.assertEqual(prefs.device_id, "5_6_7_8")
        
        # Customize device_id
        prefs.device_id = "lab-A"
        
        # Change host, device_id should NOT follow anymore
        prefs.host = "9.10.11.12"
        self.assertEqual(prefs.device_id, "lab-A")
        
        # Blank device_id, should it follow again? 
        # According to the spec: "Blanking it alone won't re-derive... 
        # but the next host change will."
        prefs.device_id = ""
        prefs.host = "192.168.1.1"
        self.assertEqual(prefs.device_id, "192_168_1_1")

    def test_port_fallback_on_missing_env(self):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("REMOTE_SSH_PORT", None)
            prefs = SSHControlPreferences()
            self.assertEqual(prefs._port_default(), 22)

    def test_port_fallback_on_garbage_env(self):
        with patch.dict(os.environ, {"REMOTE_SSH_PORT": "not-a-number"}):
            prefs = SSHControlPreferences()
            self.assertEqual(prefs._port_default(), 22)

    def test_remote_experiments_path_default(self):
        prefs = SSHControlPreferences()
        self.assertEqual(
            prefs._remote_experiments_path_default(),
            "~/Documents/Sci-Bots/Microdrop/Experiments/",
        )

if __name__ == "__main__":
    unittest.main()
