"""Offline checks of deployment templates and private configuration activation."""
import contextlib
import importlib.util
import io
import os
import json
import pwd
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('prepare_bank_web', Path(__file__).resolve().parents[1] / 'scripts/prepare_bank_web.py')
deploy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(deploy)


class DeploymentTests(unittest.TestCase):
    def test_hostname_validation(self):
        self.assertEqual(deploy.hostname('VPS.Example.org'), 'vps.example.org')
        for value in ('https://example.org', 'example.org/path', 'a.org;id', 'a.org\nroot',
                      'a..org', '-a.org', 'a-.org', 'a.org:443', 'a.org.', 'é.org',
                      '127.0.0.1', 'localhost', 'a' * 64 + '.org'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                deploy.hostname(value)

    def test_reusable_safe_templates(self):
        unit, caddy = deploy.render('personal.example.org', Path('/srv/other finance'), Path('/srv/private sessions'), 'alice', '/home/alice')
        self.assertIn('User=alice\n', unit)
        self.assertIn('WorkingDirectory=/srv/other finance\n', unit)
        self.assertNotIn('WorkingDirectory="', unit)
        self.assertIn('ReadWritePaths="/srv/private sessions"', unit)
        self.assertIn('"/srv/other finance/.venv/bin/python" -B', unit)
        self.assertIn('ProtectHome=read-only', unit)
        self.assertIn('NoNewPrivileges=true', unit)
        self.assertIn('StandardError=null', unit)
        self.assertNotIn('edouard', unit + caddy)
        self.assertIn('personal.example.org {', caddy)
        self.assertIn('admin off', caddy)
        self.assertIn('output discard', caddy)
        self.assertIn('include tls.obtain tls.issuance.acme', caddy)
        self.assertIn('log certificates {', caddy)
        self.assertIn('127.0.0.1:8765', caddy)
        self.assertIn('header_up X-Forwarded-Proto https', caddy)
        self.assertIn('header_up -Forwarded', caddy)
        self.assertNotIn('log {', caddy.split('personal.example.org {')[1])

    def config(self, root):
        directory = Path(root) / 'private'
        directory.mkdir(mode=0o700)
        environment = directory / 'environment'
        environment.write_text("# keep\nENABLE_BANKING_APP_ID='private-id'\nMULTILINE='first\nFINANCE_AUTH_REDIRECT_URL=inside-secret\nlast'\nFINANCE_AUTH_REDIRECT_URL='https://old.example/callback'\n")
        environment.chmod(0o600)
        return directory, environment

    def test_activation_preserves_secrets_and_password(self):
        from dotenv import dotenv_values
        with tempfile.TemporaryDirectory() as root:
            directory, environment = self.config(root)
            original = environment.read_text()
            output = io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                deploy.activate('bank.example.org', directory)
            values = dotenv_values(environment)
            self.assertEqual(values['ENABLE_BANKING_APP_ID'], 'private-id')
            self.assertEqual(values['MULTILINE'], 'first\nFINANCE_AUTH_REDIRECT_URL=inside-secret\nlast')
            self.assertEqual(values['FINANCE_AUTH_REDIRECT_URL'], 'https://bank.example.org/callback')
            self.assertTrue(environment.read_text().startswith('# keep\n'))
            password = (directory / 'web-password').read_text()
            deploy.activate('bank.example.org', directory)
            self.assertEqual((directory / 'web-password').read_text(), password)
            self.assertEqual(output.getvalue(), '')
            self.assertTrue(any(p.read_text() == original for p in directory.glob('environment.before-web-*')))
            for path in directory.iterdir():
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_failed_replace_keeps_environment(self):
        with tempfile.TemporaryDirectory() as root:
            directory, environment = self.config(root)
            original = environment.read_bytes()
            with patch.object(deploy.os, 'replace', side_effect=OSError('disk error')):
                with self.assertRaises(OSError):
                    deploy.activate('bank.example.org', directory)
            self.assertEqual(environment.read_bytes(), original)
            self.assertFalse(list(directory.glob('.environment-*')))

    def test_refuses_unsafe_private_paths(self):
        with tempfile.TemporaryDirectory() as root:
            directory, environment = self.config(root)
            environment.chmod(0o644)
            with self.assertRaises(ValueError):
                deploy.activate('bank.example.org', directory)
            environment.chmod(0o600)
            password = directory / 'web-password'
            password.symlink_to(environment)
            with self.assertRaises(ValueError):
                deploy.activate('bank.example.org', directory)
            password.unlink()
            directory.chmod(0o755)
            with self.assertRaises(ValueError):
                deploy.activate('bank.example.org', directory)

    def diagnostic(self, root, configuration_matches=True):
        directory = Path(root)
        binary = directory / 'bin'; binary.mkdir()
        log = directory / 'commands'
        fixture = directory / 'journal'
        fixture.write_text('\n'.join(json.dumps(row) for row in [
            {'logger': 'http.log.error', 'msg': 'bank-code-secret'},
            {'logger': 'tls.handshake', 'msg': 'not-issuance'},
            {'logger': 'tls.obtain', 'level': 'error', 'msg': 'certificate failed',
             'error': 'https://ca.example/order?token=certificate-secret'},
            {'logger': 'tls.issuance.acme.acme_client', 'msg': 'challenge rejected'},
        ]))
        commands = {
            'id': 'echo 0', 'runuser': ':', 'caddy': ':',
            'cmp': 'exit ' + ('0' if configuration_matches else '1'),
            'cp': ':', 'install': 'echo install >> "$DIAG_COMMANDS"',
            'systemctl': 'echo "$*" >> "$DIAG_COMMANDS"', 'sleep': ':',
            'journalctl': 'cat "$DIAG_FIXTURE"',
        }
        for name, body in commands.items():
            path = binary / name
            path.write_text('#!/bin/sh\n' + body + '\n'); path.chmod(0o700)
        environment = {**os.environ, 'PATH': str(binary) + os.pathsep + os.defpath,
                       'SUDO_USER': pwd.getpwuid(os.getuid()).pw_name,
                       'DIAG_COMMANDS': str(log), 'DIAG_FIXTURE': str(fixture)}
        script = Path(__file__).resolve().parents[1] / 'scripts/diagnose_bank_tls.sh'
        result = subprocess.run(['/bin/sh', str(script), 'vps.example.org'], env=environment,
                                capture_output=True, text=True, timeout=10)
        return result, log.read_text() if log.exists() else ''

    def test_diagnostic_emits_only_certificate_logs_and_redacts_queries(self):
        with tempfile.TemporaryDirectory() as root:
            result, commands = self.diagnostic(root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('certificate failed', result.stdout)
        self.assertIn('challenge rejected', result.stdout)
        self.assertNotIn('bank-code-secret', result.stdout)
        self.assertNotIn('not-issuance', result.stdout)
        self.assertNotIn('certificate-secret', result.stdout)
        self.assertIn('?[redacted]', result.stdout)
        self.assertEqual(commands.splitlines(), ['install', 'restart caddy.service'])

    def test_diagnostic_preserves_independently_changed_configuration(self):
        with tempfile.TemporaryDirectory() as root:
            result, commands = self.diagnostic(root, configuration_matches=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(commands, '')
        self.assertIn('Configuration modifiée', result.stderr)

    def test_invalid_environment_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as root:
            directory, environment = self.config(root)
            environment.write_text("SECRET='unterminated")
            with self.assertRaises(ValueError):
                deploy.activate('bank.example.org', directory)
            self.assertEqual(environment.read_text(), "SECRET='unterminated")


if __name__ == '__main__':
    unittest.main()
