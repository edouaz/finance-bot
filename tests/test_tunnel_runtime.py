import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from finance.tunnel_runtime import credential_reference, configure

class TunnelRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory()
        self.path=Path(self.directory.name)/'key'
        self.loc=patch('finance.tunnel_runtime.key_path',return_value=self.path); self.loc.start()
        self.env=patch.dict(os.environ,{},clear=True);self.env.start()
    def tearDown(self):
        self.env.stop();self.loc.stop();self.directory.cleanup()
    def test_missing_key(self):
        with self.assertRaisesRegex(RuntimeError,'key_missing'): credential_reference()
    def test_inherited_env(self):
        with patch.dict(os.environ,{'CONTROL_PLANE_API_KEY':'synthetic-test-only'}):
            self.assertEqual(credential_reference(),'env:CONTROL_PLANE_API_KEY')
    def test_private_file_reference_only(self):
        self.path.write_text('synthetic-test-only');self.path.chmod(0o600)
        self.assertEqual(credential_reference(),'file:'+str(self.path))
    def test_insecure_permissions_rejected(self):
        self.path.touch();self.path.chmod(0o644)
        with self.assertRaisesRegex(RuntimeError,'unsafe_tunnel_key'): credential_reference()
    def test_symlink_rejected(self):
        target=Path(self.directory.name)/'real';target.touch();target.chmod(0o600);self.path.symlink_to(target)
        with self.assertRaisesRegex(RuntimeError,'unsafe_tunnel_key'): credential_reference()
    def test_configure_does_not_overwrite(self):
        self.path.write_text('existing');self.path.chmod(0o600)
        with self.assertRaisesRegex(RuntimeError,'already_configured'): configure()
        self.assertEqual(self.path.read_text(),'existing')
    def test_configure_saves_private_key(self):
        with patch('sys.stdin.isatty',return_value=True),patch('getpass.getpass',return_value='synthetic-test-only'):
            configure()
        self.assertEqual(self.path.stat().st_mode & 0o777,0o600)
        self.assertEqual(self.path.read_text(),'synthetic-test-only\n')
