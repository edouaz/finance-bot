"""Stable tunnel entrypoint: the existing finance-bot profile now launches v2."""
from pathlib import Path
from dotenv import dotenv_values
import os


def load_environment():
    path = Path.home() / '.config/finance-tracker/environment'
    if path.exists():
        if path.stat().st_mode & 0o077:
            raise RuntimeError('unsafe_environment_permissions')
        for name, value in dotenv_values(path).items():
            if name in {'ENABLE_BANKING_APP_ID', 'ENABLE_BANKING_KEY', 'FINANCE_SESSIONS', 'FINANCE_STORAGE', 'FINANCE_DATA_KEY'} and value is not None:
                os.environ.setdefault(name, value)


if __name__ == '__main__':
    load_environment()
    from finance_mcp_v2 import mcp
    mcp.run(transport='stdio')
