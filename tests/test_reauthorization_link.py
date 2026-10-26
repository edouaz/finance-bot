"""The MCP renewal shortcut returns a private URL without starting bank access."""
import asyncio
import os
import unittest
from unittest.mock import patch

import finance_mcp_v2 as api


class ReauthorizationLinkTests(unittest.TestCase):
    def setUp(self):
        api._calls.clear()
        self.notices = patch.object(api, 'connection_notices', return_value=[])
        self.notices.start()
        self.addCleanup(self.notices.stop)

    def call(self, configured, bank='bnp'):
        with patch.dict(os.environ, {'FINANCE_AUTH_REDIRECT_URL': configured}):
            return api.get_reauthorization_link(bank)

    def test_both_banks_use_only_private_root_and_bank(self):
        for bank in ('bnp', 'revolut'):
            with self.subTest(bank=bank):
                result = self.call('https://private.example:8443/callback', bank)
                self.assertEqual(result['bank'], bank)
                self.assertEqual(result['url'], f'https://private.example:8443/?bank={bank}')
                self.assertEqual(set(result), {'bank', 'url', 'action'})
                self.assertNotIn('enablebanking', str(result).lower())

    def test_valid_hostnames_addresses_and_ports(self):
        for configured, expected in (
            ('https://PRIVATE.example/callback', 'https://private.example/?bank=bnp'),
            ('https://127.0.0.1:443/callback', 'https://127.0.0.1:443/?bank=bnp'),
            ('https://[::1]:8443/callback', 'https://[::1]:8443/?bank=bnp'),
            ('https://v2202609422403526649.hotsrv.de/callback',
             'https://v2202609422403526649.hotsrv.de/?bank=bnp'),
        ):
            with self.subTest(configured=configured):
                self.assertEqual(self.call(configured)['url'], expected)

    def test_missing_or_invalid_configuration_has_safe_error_without_fallback(self):
        invalid = (
            '', 'http://private.example/callback', '//private.example/callback',
            'https://edouaz.github.io/finance-bot/callback.html',
            'https://private.example/', 'https://private.example/callback/',
            'https://private.example/%63allback', 'https://private.example/../callback',
            'https://private.example/callback?code=bank-secret',
            'https://private.example/callback#bank-secret',
            'https://private.example/callback?', 'https://private.example/callback#',
            'https://finance:bank-secret@private.example/callback',
            'https://@private.example/callback', 'https://private.example:/callback',
            'https://private.example:0/callback', 'https://private.example:65536/callback',
            'https://private.example:invalid/callback', 'https:///callback',
            'https://private.example\\@evil.example/callback',
            'https://private.example\n/callback', ' https://private.example/callback',
            'https://private.example /callback', 'https://-private.example/callback',
            'https://private..example/callback', 'https://private_example/callback',
            'https://private.example\x01/callback', 'https://[::1/callback',
            'javascript:alert(1)', 'https://private.example/<script>alert(1)</script>',
        )
        for configured in invalid:
            with self.subTest(configured=configured):
                self.assertEqual(self.call(configured), {'error': 'private_web_not_configured'})
        with patch.dict(os.environ):
            os.environ.pop('FINANCE_AUTH_REDIRECT_URL', None)
            self.assertEqual(api.get_reauthorization_link('bnp'), {'error': 'private_web_not_configured'})

    def test_bank_is_required_enum_and_runtime_injections_rejected(self):
        for bank in ('all', '', 'bnp&code=secret', '../revolut', None):
            with self.subTest(bank=bank):
                self.assertEqual(self.call('https://private.example/callback', bank), {'error': 'invalid_bank'})

    def test_no_bank_network_auth_or_store_access(self):
        with patch.object(api, 'service', side_effect=AssertionError('service accessed')) as service, \
                patch.object(api, 'Store', side_effect=AssertionError('store constructed')) as store, \
                patch.object(api, 'Client', side_effect=AssertionError('client constructed')) as client, \
                patch('bank_auth.Authorization', side_effect=AssertionError('authorization constructed')) as auth, \
                patch('requests.sessions.Session.request', side_effect=AssertionError('network contacted')) as network:
            self.assertIn('url', self.call('https://private.example/callback'))
            for mocked in (service, store, client, auth, network): mocked.assert_not_called()

    def test_discovery_count_read_only_annotations_and_schema(self):
        tools = asyncio.run(api.mcp.list_tools())
        self.assertEqual(len(tools), 17)
        tool = next(t for t in tools if t.name == 'get_reauthorization_link')
        self.assertTrue(tool.annotations.readOnlyHint)
        self.assertTrue(tool.annotations.idempotentHint)
        self.assertFalse(tool.annotations.destructiveHint)
        self.assertFalse(tool.annotations.openWorldHint)
        self.assertEqual(tool.inputSchema['required'], ['bank'])
        self.assertEqual(tool.inputSchema['properties']['bank']['enum'], ['bnp', 'revolut'])

    def test_sdk_rejects_invalid_bank(self):
        with self.assertRaises(Exception):
            asyncio.run(api.mcp.call_tool('get_reauthorization_link', {'bank': 'all'}))


if __name__ == '__main__':
    unittest.main()
