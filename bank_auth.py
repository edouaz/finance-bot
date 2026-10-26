"""Operator-only AIS consent flow shared by the CLI and private web UI."""
import hashlib
import hmac
import json
import os
import secrets
import shlex
import sqlite3
import sys
import tempfile
import time
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from getpass import getpass
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import requests
from finance.core import Client, FinanceError, Settings

BANKS = {'bnp': 'BNP Paribas Fortis', 'revolut': 'Revolut'}
REDIRECT_URL = 'https://edouaz.github.io/finance-bot/callback.html'
TTL = 1800


def fingerprint(value):
    return hashlib.sha256(value.encode()).hexdigest()


class Authorization:
    def __init__(self, settings=None, redirect=None, client=None):
        self.settings = settings or Settings.load()
        self.client = client or Client(self.settings)
        self.redirect = redirect or os.environ.get('FINANCE_AUTH_REDIRECT_URL', REDIRECT_URL)
        parsed = urlsplit(self.redirect)
        if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment):
            raise FinanceError('invalid_redirect_configuration')
        self.settings.sessions.mkdir(parents=True, mode=0o700, exist_ok=True)
        if self.settings.sessions.stat().st_mode & 0o077:
            raise FinanceError('unsafe_sessions_directory')
        self.path = self.settings.sessions / 'authorization.sqlite3'
        fd = os.open(self.path, os.O_CREAT | os.O_WRONLY | os.O_NOFOLLOW, 0o600)
        os.close(fd)
        if self.path.stat().st_mode & 0o077:
            raise FinanceError('unsafe_authorization_permissions')
        with self.connect() as db:
            db.execute('CREATE TABLE IF NOT EXISTS pending (state TEXT PRIMARY KEY, bank TEXT, browser TEXT, created REAL)')

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            with db: yield db
        finally:
            db.close()

    def post(self, path, payload):
        # Consent POSTs cannot be retried safely after an uncertain network result.
        try:
            response = self.client.http.post(
                'https://api.enablebanking.com' + path, json=payload,
                headers={'Authorization': 'Bearer ' + self.client.token(), 'Accept': 'application/json'},
                timeout=(5, 25), allow_redirects=False)
            if response.status_code != 200:
                raise FinanceError(f'provider_http_{response.status_code}')
            data = response.json()
        except requests.RequestException:
            raise FinanceError('network_unavailable') from None
        except ValueError:
            raise FinanceError('invalid_provider_json') from None
        if not isinstance(data, dict):
            raise FinanceError('invalid_provider_schema')
        return data

    def start(self, bank, browser):
        if bank not in BANKS: raise FinanceError('invalid_bank')
        registry = self.client.get('/aspsps', {'country': 'BE'})
        entries = registry.get('aspsps')
        if not isinstance(entries, list) or any(not isinstance(a, dict) for a in entries):
            raise FinanceError('invalid_provider_schema')
        matches = [a for a in entries if a.get('name') == BANKS[bank] and a.get('country') == 'BE']
        if len(matches) != 1:
            raise FinanceError('bank_consent_limit_unavailable')
        seconds = matches[0].get('maximum_consent_validity')
        if type(seconds) is not int or seconds <= 0:
            raise FinanceError('bank_consent_limit_unavailable')
        try:
            valid_until = (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()
        except OverflowError:
            raise FinanceError('bank_consent_limit_unavailable') from None
        state = secrets.token_urlsafe(32)
        result = self.post('/auth', {
            'access': {'valid_until': valid_until,
                       'balances': True, 'transactions': True},
            'aspsp': {'name': BANKS[bank], 'country': 'BE'},
            'state': state, 'redirect_url': self.redirect, 'psu_type': 'personal'})
        target = result.get('url')
        if not isinstance(target, str): raise FinanceError('invalid_authorization_url')
        # Enable Banking currently serves both origins during its migration.
        parsed = urlsplit(target)
        if (parsed.scheme != 'https' or parsed.hostname not in ('auth.enablebanking.com', 'tilisy.enablebanking.com')
                or parsed.port not in (None, 443) or parsed.username or parsed.password):
            raise FinanceError('invalid_authorization_url')
        with self.connect() as db:
            db.execute('DELETE FROM pending WHERE created <= ?', (time.time() - TTL,))
            db.execute('INSERT INTO pending VALUES (?,?,?,?)',
                       (fingerprint(state), bank, fingerprint(browser), time.time()))
        return target

    def finish(self, params, browser, bank=None):
        if any(len(v) != 1 for v in params.values()): raise FinanceError('invalid_callback')
        state = params.get('state', [''])[0]
        if not state or len(state) > 512: raise FinanceError('invalid_state')
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT bank,browser,created FROM pending WHERE state=?', (fingerprint(state),)).fetchone()
            if not row or not hmac.compare_digest(row[1], fingerprint(browser)) or (bank and bank != row[0]):
                raise FinanceError('invalid_state')
            db.execute('DELETE FROM pending WHERE state=?', (fingerprint(state),))
        # Commit consumption before contacting the provider, including on errors/timeouts.
        if not 0 <= time.time() - row[2] < TTL: raise FinanceError('expired_callback')
        code = params.get('code', [''])[0]
        if 'error' in params or not code or len(code) > 4096: raise FinanceError('authorization_denied')
        result = self.post('/sessions', {'code': code})
        if (not isinstance(result.get('session_id'), str) or not result['session_id']
                or not isinstance(result.get('accounts'), list)
                or any(not isinstance(a, dict) or not isinstance(a.get('uid'), str) or not a['uid']
                       for a in result['accounts'])):
            raise FinanceError('invalid_provider_schema')
        info = self.client.session_info(result['session_id'])
        try:
            expiry = datetime.fromisoformat(info['access']['valid_until'].replace('Z', '+00:00'))
            if info['status'] != 'AUTHORIZED' or expiry <= datetime.now(timezone.utc):
                raise FinanceError('reauthorization_required')
        except (KeyError, ValueError, TypeError, AttributeError):
            raise FinanceError('invalid_session_expiry') from None
        aspsp = info.get('aspsp', {})
        if (not isinstance(aspsp, dict) or aspsp.get('name') != BANKS[row[0]]
                or aspsp.get('country') != 'BE'):
            raise FinanceError('session_bank_mismatch')
        # Keep the one-time POST response metadata; the financial cache is never opened here.
        fd, temporary = tempfile.mkstemp(prefix='.session-', dir=self.settings.sessions)
        try:
            with os.fdopen(fd, 'w') as handle:
                json.dump(result, handle)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, self.settings.sessions / f'{row[0]}_session.json')
        finally:
            Path(temporary).unlink(missing_ok=True)
        return row[0]


def start(bank):
    target = Authorization().start(bank, 'operator-cli')
    print('Ouvre cette URL en privé :')
    print(target)
    command = shlex.join([sys.executable, str(Path(__file__).resolve()), 'finish', bank])
    print('Puis :', command)


def finish(bank):
    auth = Authorization()
    url = urlsplit(getpass('URL finale du callback (entrée masquée) : ').strip())
    expected = urlsplit(auth.redirect)
    if (url.scheme, url.netloc, url.path) != (expected.scheme, expected.netloc, expected.path) or url.fragment:
        raise FinanceError('invalid_callback_url')
    auth.finish(parse_qs(url.query, keep_blank_values=True), 'operator-cli', bank)
    print('Session vérifiée et enregistrée pour :', BANKS[bank])


ERROR_MESSAGES = {
    'application_id_not_configured': "Identifiant Enable Banking absent de la configuration privée.",
    'unsafe_environment_permissions': "Le fichier d’environnement doit avoir les permissions 0600.",
    'unsafe_key_permissions': "La clé privée doit avoir les permissions 0600.",
    'unsafe_sessions_directory': "Le dossier des sessions doit avoir les permissions 0700.",
    'unsafe_authorization_permissions': "La base des autorisations doit avoir les permissions 0600.",
    'bank_consent_limit_unavailable': "Durée maximale de consentement bancaire indisponible. Aucun consentement lancé ; réessayez plus tard.",
    'invalid_redirect_configuration': "L’URL de retour configurée doit être une URL HTTPS sans paramètres.",
    'network_unavailable': "Connexion à Enable Banking indisponible. Réessayez plus tard.",
    'invalid_authorization_url': "Enable Banking a renvoyé une URL d’autorisation non autorisée. Aucun lien ouvert.",
    'invalid_provider_json': "Réponse Enable Banking illisible ; contenu masqué.",
    'invalid_provider_schema': "Réponse Enable Banking inattendue ; contenu masqué.",
    'invalid_state': "Aucune autorisation correspondante : state invalide ou déjà utilisé. Relancez start.",
    'expired_callback': "Autorisation expirée après 30 minutes. Relancez start.",
    'invalid_callback': "Paramètres de retour invalides. Relancez start.",
    'invalid_callback_url': "L’URL de retour ne correspond pas au callback configuré.",
    'authorization_denied': "Autorisation refusée ou code absent. Relancez start.",
    'reauthorization_required': "La nouvelle session bancaire n’est pas autorisée ou a expiré. Ancienne session conservée.",
    'invalid_session_expiry': "Expiration de la nouvelle session invalide. Ancienne session conservée.",
    'session_bank_mismatch': "La session ne correspond pas à la banque choisie. Ancienne session conservée.",
    **{f'provider_http_{status}': f"Enable Banking refuse la demande (HTTP {status}). Réponse masquée."
       for status in (400, 401, 403, 404, 408, 422, 429, 500, 502, 503, 504)},
}


def main():
    from finance_mcp import load_environment
    if len(sys.argv) != 3 or sys.argv[2] not in BANKS or sys.argv[1] not in ('start', 'finish'):
        print('Usage: .venv/bin/python bank_auth.py start|finish bnp|revolut', file=sys.stderr)
        return 1
    try:
        load_environment()
        {'start': start, 'finish': finish}[sys.argv[1]](sys.argv[2])
    except Exception as error:
        print(ERROR_MESSAGES.get(str(error), 'Autorisation échouée ; détails sensibles masqués.'), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
