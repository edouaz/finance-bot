"""Private reauthorization UI; opt-in process, separate from the stdio MCP."""
import base64
import binascii
import hmac
import os
import secrets
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from starlette.applications import Starlette
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, PlainTextResponse, RedirectResponse
from starlette.routing import Route

from bank_auth import Authorization, BANKS
from finance.core import FinanceError

COOKIE = '__Host-finance-auth'


def create_app(auth=None, password=None):
    auth = auth or Authorization()
    if password is None:
        path = Path(os.environ['FINANCE_AUTH_PASSWORD_FILE'])
        if path.is_symlink() or path.stat().st_mode & 0o077:
            raise FinanceError('unsafe_web_password_permissions')
        password = path.read_text().strip()
    if len(password) < 32 or ':' in password or not password.isascii():
        raise FinanceError('invalid_web_password')
    redirect = urlsplit(auth.redirect)
    if redirect.path != '/callback': raise FinanceError('web_callback_must_be_slash_callback')
    origin = f'https://{redirect.netloc}'
    expected = ('finance:' + password).encode()

    def authenticated(request):
        try:
            scheme, value = request.headers.get('authorization', '').split(' ', 1)
            return scheme.lower() == 'basic' and hmac.compare_digest(base64.b64decode(value, validate=True), expected)
        except (ValueError, binascii.Error):
            return False

    def browser(request):
        value = request.cookies.get(COOKIE, '')
        return value if len(value) == 43 and all(c.isalnum() or c in '-_' for c in value) else ''

    def home(request):
        selected = request.query_params.getlist('bank')
        if selected and (len(selected) != 1 or selected[0] not in BANKS):
            return PlainTextResponse('Banque inconnue.', status_code=400)
        banks = {selected[0]: BANKS[selected[0]]} if selected else BANKS
        token = browser(request) or secrets.token_urlsafe(32)
        result = request.query_params.get('result')
        message = {'success': 'Session vérifiée et enregistrée.',
                   'failed': 'Autorisation échouée ou expirée. Relancez le flux.'}.get(result, '')
        forms = ''.join(f'<form method="post" action="/authorize/{bank}">'
                        f'<input type="hidden" name="csrf" value="{token}">'
                        f'<button type="submit">Réautoriser {name}</button></form>'
                        for bank, name in banks.items())
        response = HTMLResponse('<!doctype html><html lang="fr"><meta charset="utf-8">'
                                '<meta name="viewport" content="width=device-width,initial-scale=1">'
                                '<title>Autorisations bancaires</title><h1>Autorisations bancaires</h1>'
                                f'<p role="status">{message}</p>{forms}</html>')
        response.set_cookie(COOKIE, token, secure=True, httponly=True, samesite='lax', max_age=1800, path='/')
        return response

    async def launch(request):
        if request.headers.get('origin') != origin or not browser(request):
            return PlainTextResponse('Requête refusée.', status_code=403)
        if request.headers.get('content-type', '').split(';')[0] != 'application/x-www-form-urlencoded':
            return PlainTextResponse('Requête refusée.', status_code=400)
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 1024: return PlainTextResponse('Requête refusée.', status_code=400)
        params = parse_qs(body.decode('ascii'), keep_blank_values=True)
        if params.get('csrf') != [browser(request)]:
            return PlainTextResponse('Requête refusée.', status_code=403)
        # Blocking provider calls run outside the ASGI event loop.
        from starlette.concurrency import run_in_threadpool
        target = await run_in_threadpool(auth.start, request.path_params['bank'], browser(request))
        return RedirectResponse(target, status_code=303)

    def callback(request):
        if len(request.scope.get('query_string', b'')) > 8192 or not browser(request):
            return RedirectResponse('/?result=failed', status_code=303)
        try:
            auth.finish(parse_qs(request.url.query, keep_blank_values=True), browser(request))
        except Exception:
            return RedirectResponse('/?result=failed', status_code=303)
        return RedirectResponse('/?result=success', status_code=303)

    app = Starlette(routes=[Route('/', home), Route('/authorize/{bank}', launch, methods=['POST']),
                            Route('/callback', callback)], debug=False)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=[redirect.hostname])

    async def private(request: Request, call_next):
        if request.url.scheme != 'https' or request.url.netloc != redirect.netloc:
            response = PlainTextResponse('HTTPS requis.', status_code=400)
        elif not authenticated(request):
            response = PlainTextResponse('Authentification requise.', status_code=401,
                                         headers={'WWW-Authenticate': 'Basic realm="Finance", charset="UTF-8"'})
        else:
            try:
                response = await call_next(request)
            except Exception:
                response = PlainTextResponse('Opération indisponible. Relancez le flux.', status_code=502)
        # Bank redirects use varying HTTPS hosts after the validated provider URL.
        response.headers.update({'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer',
                                 'Content-Security-Policy': "default-src 'none'; form-action 'self' https:; frame-ancestors 'none'; base-uri 'none'",
                                 'X-Content-Type-Options': 'nosniff', 'Strict-Transport-Security': 'max-age=31536000'})
        return response

    app.add_middleware(BaseHTTPMiddleware, dispatch=private)
    return app


if __name__ == '__main__':
    from finance_mcp import load_environment
    load_environment()
    import uvicorn
    # Only a local trusted TLS proxy may set X-Forwarded-Proto. Never bind publicly.
    uvicorn.run(create_app(), host='127.0.0.1', port=8765, access_log=False,
                log_level='critical', proxy_headers=True, forwarded_allow_ips='127.0.0.1')
