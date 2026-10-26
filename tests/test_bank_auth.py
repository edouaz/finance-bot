"""Private consent flow: no provider calls or real financial files."""
import json
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import Mock, patch

import requests

from bank_auth import Authorization, BANKS, TTL, fingerprint
from finance.core import FinanceError, Settings


class AuthorizationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.sessions = self.root / 'sessions'
        self.settings = Settings(self.root, self.root / 'storage', 'application', self.root / 'key', self.sessions)
        self.client = Mock()
        self.client.token.return_value = 'test-jwt'
        self.client.get.return_value = {'aspsps': [
            {'name': name, 'country': 'BE', 'maximum_consent_validity': 180 * 86400}
            for name in BANKS.values()]}
        self.response = Mock(status_code=200)
        self.client.http.post.return_value = self.response
        self.auth = Authorization(self.settings, 'https://finance.example/auth/callback', self.client)
        self.history = self.root / 'finance.sqlite3'
        self.history.write_bytes(b'historical transactions sentinel')
        self.old = self.sessions / 'bnp_session.json'
        self.old.write_text('{"session_id": "previous-session"}')
        self.old.chmod(0o600)

    def start(self, bank='bnp', browser='private-browser'):
        self.response.json.return_value = {'url': 'https://auth.enablebanking.com/authorize'}
        self.auth.start(bank, browser)
        state = self.client.http.post.call_args.kwargs['json']['state']
        self.response.json.return_value = {
            'session_id': 'new-session',
            'accounts': [{'uid': 'new-account', 'identification_hash': 'stable-identity'}],
            'one_time_metadata': 'keep-me',
        }
        self.client.session_info.return_value = {
            'status': 'AUTHORIZED', 'access': {'valid_until': '2099-01-01T00:00:00Z'},
            'aspsp': {'name': BANKS[bank], 'country': 'BE'},
        }
        return {'state': [state], 'code': ['private-code']}

    def finish(self, params, browser='private-browser'):
        return self.auth.finish(params, browser)

    def assert_old_untouched(self):
        self.assertEqual(json.loads(self.old.read_text()), {'session_id': 'previous-session'})
        self.assertEqual(self.history.read_bytes(), b'historical transactions sentinel')

    def assert_consumed(self, params):
        with self.assertRaisesRegex(FinanceError, 'invalid_state'):
            self.finish(params)

    def test_success_both_banks_preserves_history_metadata_and_permissions(self):
        for bank in BANKS:
            with self.subTest(bank=bank):
                params = self.start(bank)
                self.assertEqual(self.finish(params), bank)
                session = self.sessions / f'{bank}_session.json'
                self.assertEqual(json.loads(session.read_text())['one_time_metadata'], 'keep-me')
                self.assertEqual(session.stat().st_mode & 0o777, 0o600)
                self.assertEqual(self.auth.path.stat().st_mode & 0o777, 0o600)
                self.assertEqual(self.sessions.stat().st_mode & 0o777, 0o700)
                self.assertEqual(self.history.read_bytes(), b'historical transactions sentinel')
                self.assert_consumed(params)
                self.client.session_info.assert_called_with('new-session')
                call = self.client.http.post.call_args
                self.assertFalse(call.kwargs['allow_redirects'])
                self.assertEqual(call.kwargs['json'], {'code': 'private-code'})

    def test_invalid_state_and_browser_do_not_exchange_code(self):
        params = self.start()
        for supplied, browser in [({'state': ['unknown'], 'code': ['secret']}, 'private-browser'),
                                  (params, 'other-browser'), ({'code': ['secret']}, 'private-browser')]:
            with self.subTest(browser=browser, supplied=supplied):
                with self.assertRaisesRegex(FinanceError, 'invalid_state'):
                    self.finish(supplied, browser)
        self.assertEqual(self.client.http.post.call_count, 1)
        self.assert_old_untouched()
        self.assertEqual(self.finish(params), 'bnp')

    def test_wrong_bank_does_not_consume_state(self):
        params = self.start()
        with self.assertRaisesRegex(FinanceError, 'invalid_state'):
            self.auth.finish(params, 'private-browser', 'revolut')
        self.assertEqual(self.finish(params), 'bnp')

    def test_expired_and_future_callbacks_are_consumed(self):
        for offset in [-TTL - 1, 60]:
            params = self.start()
            with self.auth.connect() as db:
                db.execute('UPDATE pending SET created=created+? WHERE state=?',
                           (offset, fingerprint(params['state'][0])))
            with self.assertRaisesRegex(FinanceError, 'expired_callback'):
                self.finish(params)
            self.assert_consumed(params)
            self.assert_old_untouched()

    def test_duplicate_parameters_rejected(self):
        for name in ('state', 'code', 'error'):
            params = self.start()
            params[name] = params.get(name, ['access_denied']) * 2
            with self.assertRaisesRegex(FinanceError, 'invalid_callback'):
                self.finish(params)
        self.assertEqual(self.client.http.post.call_count, 3)
        self.assert_old_untouched()

    def test_denied_missing_and_oversized_codes_consume_state(self):
        for fields in ({'error': ['access_denied'], 'error_description': ['sensitive']},
                       {}, {'code': ['x' * 4097]}):
            params = self.start()
            params.pop('code')
            params.update(fields)
            with self.assertRaisesRegex(FinanceError, 'authorization_denied'):
                self.finish(params)
            self.assert_consumed(params)
            self.assert_old_untouched()

    def test_provider_failures_preserve_old_session_and_consume_state(self):
        for failure in ('http', 'network', 'json', 'schema'):
            with self.subTest(failure=failure):
                self.response.status_code = 200
                self.response.json.side_effect = None
                self.client.http.post.side_effect = None
                params = self.start()
                if failure == 'http': self.response.status_code = 500
                if failure == 'network': self.client.http.post.side_effect = requests.Timeout('secret-code')
                if failure == 'json': self.response.json.side_effect = ValueError('secret-code')
                if failure == 'schema': self.response.json.return_value = []
                with self.assertRaises(FinanceError) as caught:
                    self.finish(params)
                self.assertNotIn('secret-code', str(caught.exception))
                self.assert_consumed(params)
                self.assert_old_untouched()

    def test_session_validation_failure_preserves_old_session(self):
        for failure in ('reauthorization_required', 'invalid_session_expiry', 'network_unavailable'):
            params = self.start()
            self.client.session_info.side_effect = FinanceError(failure)
            with self.assertRaisesRegex(FinanceError, failure):
                self.finish(params)
            self.assert_consumed(params)
            self.assert_old_untouched()
            self.client.session_info.side_effect = None

    def test_bank_mismatch_preserves_old_session(self):
        params = self.start()
        self.client.session_info.return_value['aspsp']['name'] = 'Revolut'
        with self.assertRaisesRegex(FinanceError, 'session_bank_mismatch'):
            self.finish(params)
        self.assert_consumed(params)
        self.assert_old_untouched()

    def test_failed_atomic_replace_preserves_old_session_and_removes_temporary(self):
        params = self.start()
        with patch('bank_auth.os.replace', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.finish(params)
        self.assert_consumed(params)
        self.assert_old_untouched()
        self.assertEqual(list(self.sessions.glob('.session-*')), [])

    def test_concurrent_callbacks_exchange_only_once(self):
        params = self.start()
        barrier = threading.Barrier(2)
        def callback():
            barrier.wait(timeout=5)
            try: return self.finish(params)
            except FinanceError as error: return str(error)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: callback(), range(2)))
        self.assertCountEqual(results, ['bnp', 'invalid_state'])
        self.assertEqual(self.client.http.post.call_count, 2)

    def test_untrusted_authorization_url_is_rejected(self):
        for target in ('http://auth.enablebanking.com/start', 'https://evil.example/start',
                       'https://auth.enablebanking.com.evil.example/',
                       'https://tilisy.enablebanking.com.evil.example/',
                       'https://attacker.enablebanking.com/',
                       'http://tilisy.enablebanking.com/',
                       'https://tilisy.enablebanking.com:444/',
                       'https://password@tilisy.enablebanking.com/',
                       'https://user:password@auth.enablebanking.com/', None):
            self.response.json.return_value = {'url': target}
            with self.assertRaisesRegex(FinanceError, 'invalid_authorization_url'):
                self.auth.start('bnp', 'private-browser')
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 0)

    def test_both_official_authorization_origins_are_accepted(self):
        for host in ('auth.enablebanking.com', 'tilisy.enablebanking.com'):
            target = f'https://{host}/ais/start?sessionid=synthetic-private-id'
            self.response.json.return_value = {'url': target}
            self.assertEqual(self.auth.start('bnp', 'private-browser'), target)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM pending').fetchone()[0], 2)

    def test_pending_state_is_hashed_and_access_is_read_only(self):
        params = self.start()
        with self.auth.connect() as db:
            row = db.execute('SELECT state,bank,browser FROM pending').fetchone()
        self.assertEqual(row, (fingerprint(params['state'][0]), 'bnp', fingerprint('private-browser')))
        payload = self.client.http.post.call_args.kwargs['json']
        self.assertEqual(set(payload['access']), {'valid_until', 'balances', 'transactions'})
        self.assertTrue(payload['access']['balances'])
        self.assertTrue(payload['access']['transactions'])
        self.assertEqual(payload['redirect_url'], 'https://finance.example/auth/callback')

    def test_pending_flow_survives_process_restart(self):
        params = self.start()
        restarted = Authorization(self.settings, self.auth.redirect, self.client)
        self.assertEqual(restarted.finish(params, 'private-browser'), 'bnp')
        self.assert_consumed(params)

    def test_invalid_provider_session_schema_and_status_preserve_old_session(self):
        for change in ({'status': 'CANCELLED'}, {'access': {}},
                       {'access': {'valid_until': '2000-01-01T00:00:00Z'}},
                       {'access': {'valid_until': '2099-01-01'}},
                       {'access': {'valid_until': 'not-a-date'}}):
            params = self.start()
            self.client.session_info.return_value.update(change)
            with self.assertRaises(FinanceError): self.finish(params)
            self.assert_consumed(params)
            self.assert_old_untouched()
        for change in ({'session_id': None}, {'accounts': 'invalid'}, {'accounts': [{}]}):
            params = self.start()
            self.response.json.return_value.update(change)
            with self.assertRaisesRegex(FinanceError, 'invalid_provider_schema'): self.finish(params)
            self.assert_consumed(params)
            self.assert_old_untouched()

    def test_requests_provider_maximum_without_a_ten_day_cap(self):
        from datetime import datetime, timezone
        for days in (1, 90, 180, 365):
            self.client.get.return_value['aspsps'][0]['maximum_consent_validity'] = days * 86400
            before = datetime.now(timezone.utc)
            self.start()
            expiry = datetime.fromisoformat(self.client.http.post.call_args.kwargs['json']['access']['valid_until'])
            self.assertAlmostEqual((expiry - before).total_seconds(), days * 86400, delta=2)
            self.client.get.assert_called_with('/aspsps', {'country': 'BE'})

    def test_unavailable_or_invalid_bank_limits_never_launch_authorization(self):
        for value in (None, 0, -1, True, '15552000', 1.5, 10**100):
            self.client.get.return_value['aspsps'][0]['maximum_consent_validity'] = value
            with self.assertRaisesRegex(FinanceError, 'bank_consent_limit_unavailable'):
                self.start()
        for registry in ({}, {'aspsps': []}, {'aspsps': [None]},
                         {'aspsps': [{'name': BANKS['bnp'], 'country': 'FR', 'maximum_consent_validity': 180 * 86400}]}):
            self.client.get.return_value = registry
            with self.assertRaises(FinanceError): self.start()
        self.client.get.side_effect = FinanceError('network_unavailable')
        with self.assertRaises(FinanceError): self.start()
        self.client.http.post.assert_not_called()

    def test_invalid_bank_never_contacts_provider(self):
        with self.assertRaisesRegex(FinanceError, 'invalid_bank'):
            self.auth.start('other', 'private-browser')
        self.client.http.post.assert_not_called()


class CommandLineTests(unittest.TestCase):
    def test_start_guides_finish_with_the_same_python(self):
        import contextlib
        import io
        import shlex
        import bank_auth
        output = io.StringIO()
        with patch('bank_auth.Authorization') as auth, \
             patch('bank_auth.sys.executable', '/private environment/bin/python'), \
             contextlib.redirect_stdout(output):
            auth.return_value.redirect = bank_auth.REDIRECT_URL
            auth.return_value.start.return_value = 'https://auth.enablebanking.com/synthetic'
            bank_auth.start('bnp')
        command = output.getvalue().split('Puis : ', 1)[1].strip()
        self.assertEqual(shlex.split(command), ['/private environment/bin/python',
                         str(Path(bank_auth.__file__).resolve()), 'finish', 'bnp'])

    def test_private_callback_guides_browser_flow_without_cli_state(self):
        import contextlib
        import io
        import bank_auth
        output = io.StringIO()
        with patch('bank_auth.Authorization') as auth, contextlib.redirect_stdout(output):
            auth.return_value.redirect = 'https://private.example/callback'
            bank_auth.start('revolut')
            auth.return_value.start.assert_not_called()
        self.assertIn('https://private.example/?bank=revolut', output.getvalue())
        self.assertIn('automatiquement', output.getvalue())
        self.assertNotIn(' finish ', output.getvalue())

    def test_expected_errors_are_actionable_without_exposing_payloads(self):
        import contextlib
        import io
        import bank_auth
        for code, expected in [('unsafe_sessions_directory', '0700'),
                               ('provider_http_400', 'HTTP 400'),
                               ('invalid_authorization_url', 'URL'),
                               ('application_id_not_configured', 'Identifiant')]:
            output = io.StringIO()
            with patch('sys.argv', ['bank_auth.py', 'start', 'bnp']), \
                 patch('finance_mcp.load_environment'), \
                 patch('bank_auth.Authorization', side_effect=FinanceError(code)), \
                 contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
                self.assertEqual(bank_auth.main(), 1)
            self.assertIn(expected, output.getvalue())
            self.assertNotIn('Ouvre cette URL', output.getvalue())

    def test_unknown_errors_and_environment_errors_do_not_leak(self):
        import contextlib
        import io
        import bank_auth
        for target in ('bank_auth.Authorization', 'finance_mcp.load_environment'):
            output = io.StringIO()
            with patch('sys.argv', ['bank_auth.py', 'start', 'bnp']), \
                 patch('finance_mcp.load_environment'), \
                 patch(target, side_effect=RuntimeError('bank-code-secret password-secret')), \
                 contextlib.redirect_stderr(output), contextlib.redirect_stdout(output):
                self.assertEqual(bank_auth.main(), 1)
            self.assertNotIn('secret', output.getvalue())
            self.assertIn('masqués', output.getvalue())


if __name__ == '__main__':
    unittest.main()
