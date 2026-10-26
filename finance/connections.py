"""Nonsecret consent metadata; no provider calls or changes to stored sessions."""
import json
import math
from datetime import datetime, timezone
from .core import BANKS


def connection_status(settings, at=None):
    at = at or datetime.now(timezone.utc)
    result = {}
    for bank in BANKS:
        try:
            path = settings.sessions / f'{bank}_session.json'
            if path.is_symlink() or path.stat().st_mode & 0o077:
                raise ValueError('unsafe_session')
            data = json.loads(path.read_text())
            expiry = datetime.fromisoformat(data['access']['valid_until'].replace('Z', '+00:00'))
            remaining = (expiry - at).total_seconds()
            result[bank] = {'valid_until': expiry.isoformat(), 'reauthorization_required': remaining <= 0,
                            'expires_soon': 0 < remaining <= 7 * 86400,
                            'days_remaining': max(0, math.ceil(remaining / 86400)), 'live_verified': False}
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            result[bank] = {'status': 'session_unavailable', 'live_verified': False}
    return result
