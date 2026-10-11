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


def prepare_environment(reference):
    # tunnel-client 0.0.16 resolves YAML env references before CLI overrides.
    # Supply the existing profile reference as well as the explicit file flag.
    if reference.startswith('file:'):
        value = key_path().read_text().strip()
        if not value or any(c.isspace() for c in value):
            raise RuntimeError('invalid_saved_key_format')
        os.environ['CONTROL_PLANE_API_KEY'] = value


def configure(replace=False):
    path = key_path()
    path.parent.mkdir(parents=True, mode=0o700, exist_ok=True)
    if path.parent.stat().st_mode & 0o077:
        raise RuntimeError('unsafe_config_directory_permissions')
    if path.is_symlink():
        raise RuntimeError('unsafe_tunnel_key_permissions')
    if path.exists() and not replace:
        raise RuntimeError('key_already_configured_no_overwrite')
    if not sys.stdin.isatty():
        raise RuntimeError('configure_requires_private_interactive_terminal')
    value = getpass.getpass('Clé existante du tunnel OpenAI (saisie masquée) : ').strip()
    if value.startswith('tunnel_'):
        raise RuntimeError('expected_api_key_not_tunnel_identifier')
    if not value.startswith('sk-') or len(value) < 16 or '*' in value or not value.isascii() or any(c.isspace() for c in value):
        raise RuntimeError('invalid_key_format')
    if replace:
        import tempfile
        fd, temporary = tempfile.mkstemp(prefix='.tunnel-key-', dir=path.parent)
    else:
        temporary = None
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, 'w') as handle:
            handle.write(value + '\n')
            handle.flush()
            os.fsync(handle.fileno())
        if temporary: os.replace(temporary, path)
    finally:
        if temporary and Path(temporary).exists(): Path(temporary).unlink()
    print('Clé enregistrée localement avec permissions 0600. Aucun envoi dans un chat ou dépôt.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['run', 'doctor', 'configure'], nargs='?', default='run')
    parser.add_argument('--replace', action='store_true', help='Replace only the locally saved credential, without revoking any API key')
    args = parser.parse_args()
    if args.replace and args.command != 'configure': parser.error('--replace requires configure')
    try:
        if args.command == 'configure':
            configure(replace=args.replace)
            return 0
        reference = credential_reference()
        prepare_environment(reference)
        executable = Path.home() / '.local/bin/tunnel-client'
        os.execv(executable, [str(executable), args.command, '--profile', 'finance-bot', '--control-plane.api-key', reference])
    except (RuntimeError, OSError) as exc:
        print(str(exc) if isinstance(exc, RuntimeError) else 'tunnel_startup_failed', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
