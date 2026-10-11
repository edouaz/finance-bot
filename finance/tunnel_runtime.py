"""Operator-only tunnel startup; durable credentials never exposed via MCP."""
import argparse
import getpass
import os
from pathlib import Path
import sys


def key_path():
    return Path.home() / '.config/finance-tracker/tunnel-api.key'


def credential_reference():
    path = key_path()
    if path.exists():
        if path.is_symlink() or not path.is_file() or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid():
            raise RuntimeError('unsafe_tunnel_key_permissions')
        return 'file:' + str(path)
    if os.environ.get('CONTROL_PLANE_API_KEY'):
        return 'env:CONTROL_PLANE_API_KEY'
    raise RuntimeError('tunnel_key_missing_run_configure')


def configure():
    path = key_path()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.stat().st_mode & 0o077:
        raise RuntimeError('unsafe_config_directory_permissions')
    if path.exists() or path.is_symlink():
        raise RuntimeError('key_already_configured_no_overwrite')
    if not sys.stdin.isatty():
        raise RuntimeError('configure_requires_private_interactive_terminal')
    value = getpass.getpass('Clé existante du tunnel OpenAI (saisie masquée) : ').strip()
    if len(value) < 16 or any(c.isspace() for c in value):
        raise RuntimeError('invalid_key_format')
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, 'w') as handle:
        handle.write(value + '\n')
        handle.flush()
        os.fsync(handle.fileno())
    print('Clé enregistrée localement avec permissions 0600. Aucun envoi dans un chat ou dépôt.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['run', 'doctor', 'configure'], nargs='?', default='run')
    args = parser.parse_args()
    try:
        if args.command == 'configure':
            configure()
            return 0
        reference = credential_reference()
        executable = Path.home() / '.local/bin/tunnel-client'
        os.execv(executable, [str(executable), args.command, '--profile', 'finance-bot', '--control-plane.api-key', reference])
    except (RuntimeError, OSError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else 'tunnel_startup_failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
