"""Operator-only commands; never exposed through MCP."""
import argparse
import json
import os
import sys
from pathlib import Path
from datetime import datetime,timedelta
from zoneinfo import ZoneInfo
from cryptography.fernet import Fernet
from .core import Client,Settings,FinanceError
from .store import Store
from .service import Service

def main():
    p=argparse.ArgumentParser(); commands=p.add_subparsers(dest='command',required=True)
    init=commands.add_parser('init-key'); init.add_argument('path')
    sync=commands.add_parser('sync'); sync.add_argument('--bank',choices=['all','bnp','revolut'],default='all'); sync.add_argument('--start',required=True); sync.add_argument('--end',required=True)
    report=commands.add_parser('weekly-report'); report.add_argument('--output',required=True)
    backup=commands.add_parser('backup'); backup.add_argument('destination')
    commands.add_parser('health')
    args=p.parse_args()
    try:
        from finance_mcp import load_environment
        load_environment()
        settings=Settings.load()
        if args.command=='init-key':
            target=Path(args.path).expanduser().resolve()
            if settings.root==target or settings.root in target.parents: raise FinanceError('key_must_be_outside_repository')
            target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
            fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(fd,'wb') as f: f.write(Fernet.generate_key())
            print('Encryption key created; keep an offline recovery copy.'); return
        store=Store(settings); service=Service(store,Client(settings))
        if args.command=='sync':
            result=service.sync(args.bank,args.start,args.end)
            print(json.dumps({'accounts_processed':len(result['results']),'complete':all(x['complete'] for x in result['results']),'errors':sorted({x['error'] for x in result['results'] if x.get('error')})}))
            if not result['results'] or not all(x['complete'] for x in result['results']): return 1
        elif args.command=='health':
            with store.connect() as db:
                if db.execute('PRAGMA quick_check').fetchone()[0]!='ok': raise FinanceError('database_integrity_failed')
            print('Local storage health: OK; bank/tunnel health not tested')
        elif args.command=='backup': store.backup(args.destination); print('Backup completed')
        elif args.command=='weekly-report':
            target=Path(args.output).expanduser().resolve()
            if settings.root==target or settings.root in target.parents: raise FinanceError('report_must_be_outside_repository')
            end=datetime.now(ZoneInfo('Europe/Brussels')).date()-timedelta(days=1)
            result=service.report((end-timedelta(days=6)).isoformat(),end.isoformat())
            from .analytics import recurring
            result['recurring']=recurring(service.analysis_rows((end-timedelta(days=365)).isoformat(),end.isoformat()),end)
            encrypted=store.seal(result)
            target.parent.mkdir(parents=True,mode=0o700,exist_ok=True)
            import tempfile
            fd,temporary=tempfile.mkstemp(prefix='.report-',dir=target.parent)
            try:
                with os.fdopen(fd,'wb') as f:
                    f.write(encrypted); f.flush(); os.fsync(f.fileno())
                os.replace(temporary,target)
            finally:
                if Path(temporary).exists(): Path(temporary).unlink()
            print('Encrypted weekly report created locally; no delivery attempted')
    except Exception as e:
        print(str(e) if isinstance(e,FinanceError) else 'local_operation_failed',file=sys.stderr); return 1
    return 0
if __name__=='__main__': sys.exit(main())
