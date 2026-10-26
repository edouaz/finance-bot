import contextlib
import io
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from starlette.testclient import TestClient
from bank_auth_web import create_app, COOKIE
from finance.core import FinanceError


class WebTests(unittest.TestCase):
    def setUp(self):
        # The test HTTP client must not log even synthetic callback query strings.
        for name in ('httpx', 'httpx2'):
            mute = patch.object(logging.getLogger(name), 'disabled', True)
            mute.start(); self.addCleanup(mute.stop)
        self.auth = Mock(redirect='https://finance.example/callback')
        self.auth.start.return_value = 'https://auth.enablebanking.com/start'
        self.password = 'synthetic-private-password-' + 'x' * 32
        self.app = create_app(self.auth, self.password)
        self.client = TestClient(self.app, base_url='https://finance.example',
                                 follow_redirects=False)
        self.client.auth = ('finance', self.password)
        self.addCleanup(self.client.close)

    def token(self):
        self.client.get('/')
        return self.client.cookies.get(COOKIE)

    def launch(self, **kwargs):
        token = self.token()
        return self.client.post('/authorize/bnp', data={'csrf': token},
                                headers={'Origin': 'https://finance.example'}, **kwargs)

    def test_every_route_requires_auth(self):
        for path, method in [('/', 'GET'), ('/callback?code=secret&state=secret', 'GET'), ('/authorize/bnp', 'POST')]:
            for auth in (None, ('finance', 'incorrect')):
                response = self.client.request(method, path, auth=auth)
                self.assertEqual(response.status_code, 401)
                self.assertNotIn('secret', response.text)
        self.auth.start.assert_not_called()
        self.auth.finish.assert_not_called()

    def test_home_buttons_cookie_and_security_headers(self):
        response = self.client.get('/')
        self.assertIn('Réautoriser BNP Paribas Fortis', response.text)
        self.assertIn('Réautoriser Revolut', response.text)
        cookie = response.headers['set-cookie']
        for attribute in ('Secure', 'HttpOnly', 'SameSite=lax', 'Path=/'):
            self.assertIn(attribute, cookie)
        self.assertEqual(response.headers['cache-control'], 'no-store')
        self.assertEqual(response.headers['referrer-policy'], 'no-referrer')
        self.assertIn("frame-ancestors 'none'", response.headers['content-security-policy'])
        self.assertIn("form-action 'self' https:", response.headers['content-security-policy'])
        self.assertNotIn(self.password, response.text)

    def test_mcp_link_selects_bank_without_starting_authorization(self):
        for bank, name, other in [('bnp', 'BNP Paribas Fortis', 'Revolut'),
                                  ('revolut', 'Revolut', 'BNP Paribas Fortis')]:
            response = self.client.get('/?bank=' + bank)
            self.assertEqual(response.status_code, 200)
            self.assertIn('Réautoriser ' + name, response.text)
            self.assertNotIn('Réautoriser ' + other, response.text)
        for query in ('bank=unknown', 'bank=bnp&bank=revolut', 'bank=%3Cscript%3Esecret%3C/script%3E'):
            response = self.client.get('/?' + query)
            self.assertEqual(response.status_code, 400)
            self.assertNotIn('secret', response.text)
        self.auth.start.assert_not_called()
        self.auth.finish.assert_not_called()

    def test_launch_is_post_only_with_origin_and_csrf(self):
        self.assertEqual(self.client.get('/authorize/bnp').status_code, 405)
        token = self.token()
        for data, origin in [({'csrf': token}, 'https://evil.example'), ({'csrf': 'bad'}, 'https://finance.example'),
                             ({'csrf': token}, ''), ({}, 'https://finance.example')]:
            response = self.client.post('/authorize/bnp', data=data, headers={'Origin': origin})
            self.assertEqual(response.status_code, 403 if data else 400)
        self.auth.start.assert_not_called()
        response = self.client.post('/authorize/revolut', data={'csrf': token}, headers={'Origin': 'https://finance.example'})
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], 'https://auth.enablebanking.com/start')
        self.auth.start.assert_called_once_with('revolut', token)

    def test_missing_cookie_and_oversized_body(self):
        response = self.client.post('/authorize/bnp', data={'csrf': 'x'}, headers={'Origin': 'https://finance.example'})
        self.assertEqual(response.status_code, 403)
        self.token()
        response = self.client.post('/authorize/bnp', content='x' * 1025,
                                    headers={'Origin': 'https://finance.example', 'Content-Type': 'application/x-www-form-urlencoded'})
        self.assertEqual(response.status_code, 400)
        self.auth.start.assert_not_called()

    def test_callback_cleans_url_and_never_reflects_provider_data(self):
        token = self.token()
        response = self.client.get('/callback?state=state-secret&code=bank-secret')
        self.assertEqual(response.status_code, 303)
        self.assertEqual(response.headers['location'], '/?result=success')
        self.auth.finish.assert_called_once_with({'state': ['state-secret'], 'code': ['bank-secret']}, token)
        self.auth.finish.side_effect = RuntimeError('bank-secret password-secret')
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            response = self.client.get('/callback?state=state-secret&code=bank-secret&error_description=password-secret')
        self.assertEqual(response.headers['location'], '/?result=failed')
        self.assertNotIn('secret', response.text + out.getvalue())
        response = self.client.get('/?result=<script>bank-secret</script>')
        self.assertNotIn('bank-secret', response.text)

    def test_callback_missing_cookie_rejected(self):
        self.assertEqual(self.client.get('/callback?code=secret&state=secret').headers['location'], '/?result=failed')
        self.auth.finish.assert_not_called()

    def test_exact_https_host_required(self):
        for base in ('http://finance.example', 'https://evil.example', 'https://finance.example:9999'):
            with TestClient(self.app, base_url=base) as client:
                client.auth = ('finance', self.password)
                self.assertEqual(client.get('/').status_code, 400)
        # A remote caller's forwarded header is not trusted by the application.
        with TestClient(self.app, base_url='http://finance.example') as client:
            client.auth = ('finance', self.password)
            self.assertEqual(client.get('/', headers={'X-Forwarded-Proto': 'https'}).status_code, 400)

    def test_provider_exception_sanitized(self):
        self.auth.start.side_effect = RuntimeError('secret-provider-body')
        response = self.launch()
        self.assertEqual(response.status_code, 502)
        self.assertNotIn('secret', response.text)

    def test_complete_web_flow_with_real_shared_authorization(self):
        from bank_auth import Authorization, BANKS
        from finance.core import Client, Settings
        import json
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            settings = Settings(root, root / 'storage', 'application', root / 'key', root / 'sessions')
            transport = Mock()
            provider = Client(settings, transport=transport)
            provider.token = Mock(return_value='synthetic-jwt')
            auth = Authorization(settings, 'https://finance.example/callback', provider)
            app = create_app(auth, self.password)
            with TestClient(app, base_url='https://finance.example', follow_redirects=False) as client:
                client.auth = ('finance', self.password)
                client.get('/')
                token = client.cookies.get(COOKIE)
                for bank in BANKS:
                    transport.get.return_value = Mock(status_code=200)
                    transport.get.return_value.json.return_value = {'aspsps': [
                        {'name': BANKS[bank], 'country': 'BE', 'maximum_consent_validity': 180 * 86400}]}
                    transport.post.return_value = Mock(status_code=200)
                    target = ('https://tilisy.enablebanking.com/start' if bank == 'bnp' else 'https://auth.enablebanking.com/start')
                    transport.post.return_value.json.return_value = {'url': target}
                    response = client.post('/authorize/' + bank, data={'csrf': token},
                                           headers={'Origin': 'https://finance.example'})
                    self.assertEqual(response.status_code, 303)
                    self.assertEqual(response.headers['location'], target)
                    state = transport.post.call_args.kwargs['json']['state']
                    transport.post.return_value.json.return_value = {'session_id': bank + '-session', 'accounts': [{'uid': 'account'}]}
                    transport.get.return_value = Mock(status_code=200)
                    transport.get.return_value.json.return_value = {
                        'status': 'AUTHORIZED', 'access': {'valid_until': '2099-01-01T00:00:00Z'},
                        'aspsp': {'name': BANKS[bank], 'country': 'BE'}}
                    response = client.get('/callback', params={'code': 'bank-secret', 'state': state})
                    self.assertEqual(response.headers['location'], '/?result=success')
                    saved = json.loads((settings.sessions / (bank + '_session.json')).read_text())
                    self.assertEqual(saved['session_id'], bank + '-session')
                    transport.get.assert_called_with('https://api.enablebanking.com/sessions/' + bank + '-session',
                                                     params=None, headers={'Authorization': 'Bearer synthetic-jwt', 'Accept': 'application/json'},
                                                     timeout=(5, 25))
                    calls = transport.post.call_count
                    self.assertEqual(client.get('/callback', params={'code': 'bank-secret', 'state': state}).headers['location'], '/?result=failed')
                    self.assertEqual(transport.post.call_count, calls)

    def test_password_file_must_be_private_and_configuration_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'password'
            path.write_text(self.password)
            path.chmod(0o644)
            with patch.dict(os.environ, {'FINANCE_AUTH_PASSWORD_FILE': str(path)}):
                with self.assertRaisesRegex(FinanceError, 'unsafe_web_password'):
                    create_app(self.auth)
                path.chmod(0o600)
                create_app(self.auth)
        with self.assertRaises(FinanceError): create_app(self.auth, 'short')
        with self.assertRaises(FinanceError): create_app(Mock(redirect='https://finance.example/other'), self.password)


if __name__ == '__main__': unittest.main()
