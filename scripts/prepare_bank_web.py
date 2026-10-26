#!/usr/bin/env python3
"""Prepare private web deployment files; activate config only when explicitly requested."""
import argparse
import io
import ipaddress
import os
from pathlib import Path
import pwd
import re
import secrets
import stat
import sys
import tempfile

REPO = Path(__file__).resolve().parents[1]


def hostname(value):
    if (not value.isascii() or len(value) > 253 or '.' not in value
            or any(not re.fullmatch(r'[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?', label)
                   for label in value.split('.'))):
        raise ValueError('invalid_hostname')
    try:
        ipaddress.ip_address(value)
    except ValueError:
        return value.lower()
    raise ValueError('dns_hostname_required')


def private(path, directory=False):
    for ancestor in [*reversed(path.parents), path]:
        if ancestor.is_symlink():
            raise ValueError('symlink_refused')
    info = path.stat()
    if info.st_uid != os.getuid() or info.st_mode & 0o077:
        raise ValueError('unsafe_private_permissions')
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ValueError('invalid_private_path')


def quote(value):
    value = str(value)
    if any(c in value for c in '\n\r\x00'):
        raise ValueError('invalid_service_path')
    return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%') + '"'


def render(host, repo, sessions, user, home):
    host = hostname(host)
    quote(repo)  # Validate control characters; WorkingDirectory is a scalar, not an argv list.
    unit = f'''[Unit]
Description=Private Finance bank reauthorization
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User={user}
WorkingDirectory={str(repo).replace('%', '%%')}
Environment={quote('HOME=' + str(home))}
ExecStart={quote(repo / '.venv/bin/python')} -B {quote(repo / 'bank_auth_web.py')}
UMask=0077
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths={quote(sessions)}
PrivateTmp=true
Restart=on-failure
RestartSec=5
StandardOutput=null
StandardError=null

[Install]
WantedBy=multi-user.target
'''
    caddy = f'''{{
    admin off
    log {{
        output discard
    }}
    log certificates {{
        include tls.obtain tls.issuance.acme
        output stderr
        level INFO
    }}
}}
{host} {{
    reverse_proxy 127.0.0.1:8765 {{
        header_up X-Forwarded-Proto https
        header_up -Forwarded
    }}
}}
'''
    return unit, caddy


def activate(host, config):
    host = hostname(host)
    private(config, directory=True)
    environment = config / 'environment'
    private(environment)
    password = config / 'web-password'
    if password.exists() or password.is_symlink():
        private(password)
        value = password.read_text().strip()
        if len(value) < 32 or ':' in value or not value.isascii():
            raise ValueError('invalid_web_password')
    else:
        fd = os.open(password, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, 'w') as handle:
            handle.write(secrets.token_urlsafe(48) + '\n')
    # Parse bindings to preserve comments and multiline secrets byte for byte.
    from dotenv.parser import parse_stream
    original = environment.read_text()
    bindings = list(parse_stream(io.StringIO(original)))
    if any(binding.error for binding in bindings):
        raise ValueError('invalid_environment')
    values = {'FINANCE_AUTH_REDIRECT_URL': 'https://' + host + '/callback',
              'FINANCE_AUTH_PASSWORD_FILE': str(password)}
    preserved = ''.join(binding.original.string for binding in bindings if binding.key not in values)
    escaped = lambda value: value.replace('\\', '\\\\').replace("'", "\\'")
    content = preserved + ('\n' if preserved and not preserved.endswith('\n') else '')
    content += ''.join(f"{key}='{escaped(value)}'\n" for key, value in values.items())
    backup_fd, backup = tempfile.mkstemp(prefix='environment.before-web-', dir=config)
    with os.fdopen(backup_fd, 'w') as handle:
        handle.write(original)
        handle.flush()
        os.fsync(handle.fileno())
    fd, temporary = tempfile.mkstemp(prefix='.environment-', dir=config)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, environment)
    finally:
        Path(temporary).unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--hostname', required=True, type=hostname)
    parser.add_argument('--activate-config', action='store_true')
    args = parser.parse_args()
    if os.getuid() == 0:
        raise ValueError('run_as_repository_owner_not_root')
    owner = pwd.getpwuid(os.getuid())
    if REPO.stat().st_uid != owner.pw_uid:
        raise ValueError('repository_owner_required')
    config = Path(owner.pw_dir) / '.config/finance-tracker'
    private(config, directory=True)
    if args.activate_config:
        activate(args.hostname, config)
        return
    sys.path.insert(0, str(REPO))
    from finance_mcp import load_environment
    from finance.core import Settings
    load_environment()
    settings = Settings.load()
    sessions = settings.sessions.absolute()
    private(sessions, directory=True)
    staging = REPO / 'data/web-deployment'
    private(staging.parent, directory=True)
    staging.mkdir(mode=0o700, exist_ok=True)
    private(staging, directory=True)
    service, caddy = render(args.hostname, REPO, sessions, owner.pw_name, owner.pw_dir)
    for name, content in [('finance-bank-auth.service', service), ('Caddyfile', caddy)]:
        target = staging / name
        fd = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
        with os.fdopen(fd, 'w') as handle:
            handle.write(content)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        print('Préparation refusée ; configuration privée et permissions à vérifier.', file=sys.stderr)
        sys.exit(1)
