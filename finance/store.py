"""Versioned SQLite store. Raw provider metadata encrypted with an operator key."""
import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from cryptography.fernet import Fernet
from .core import FinanceError, now

class Store:
    def __init__(self, settings):
        self.settings=settings
        settings.storage.mkdir(parents=True,mode=0o700,exist_ok=True)
        if settings.storage.stat().st_mode & 0o077: raise FinanceError('unsafe_storage_permissions')
        keypath=os.environ.get('FINANCE_DATA_KEY')
        if not keypath: raise FinanceError('data_encryption_key_not_configured')
        p=Path(keypath)
        if p.stat().st_mode & 0o077: raise FinanceError('unsafe_data_key_permissions')
        self.cipher=Fernet(p.read_bytes().strip())
        self.path=settings.storage/'finance.sqlite3'
        if self.path.exists() and self.path.stat().st_mode & 0o077: raise FinanceError('unsafe_database_permissions')
        if not self.path.exists():
            fd=os.open(self.path,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd)
        with self.connect() as db:
            version=db.execute('PRAGMA user_version').fetchone()[0]
            if version>1: raise FinanceError('unsupported_database_version')
            db.executescript('''CREATE TABLE IF NOT EXISTS accounts(id TEXT PRIMARY KEY, bank TEXT, uid BLOB, metadata BLOB, updated TEXT);
            CREATE TABLE IF NOT EXISTS transactions(id TEXT PRIMARY KEY,bank TEXT,account TEXT,date TEXT,currency TEXT,status TEXT,payload BLOB);
            CREATE INDEX IF NOT EXISTS tx_search ON transactions(bank,account,date,currency,status);
            CREATE TABLE IF NOT EXISTS balances(id INTEGER PRIMARY KEY, account TEXT, fetched TEXT,payload BLOB);
            CREATE TABLE IF NOT EXISTS syncs(id INTEGER PRIMARY KEY,account TEXT,start TEXT,end TEXT,fetched TEXT,complete INTEGER,error TEXT,count INTEGER);
            PRAGMA user_version=1;''')
    @contextmanager
    def connect(self):
        # DELETE journal avoids persistent unprotected WAL sidecars; SQLite lock + busy timeout.
        old=os.umask(0o077)
        try: db=sqlite3.connect(self.path,timeout=30)
        finally: os.umask(old)
        db.row_factory=sqlite3.Row
        try:
            with db: yield db
        finally: db.close()
    def seal(self,value): return self.cipher.encrypt(json.dumps(value,separators=(',',':')).encode())
    def unseal(self,value): return json.loads(self.cipher.decrypt(value))
    def save_account(self, bank, uid, metadata):
        from .core import digest
        # Identification hashes survive new consents; uid does not necessarily do so.
        hashes=metadata.get('identification_hash') or metadata.get('identification_hashes')
        identity=json.dumps(hashes,sort_keys=True) if hashes else uid
        aid=digest(bank+':'+identity)[:24]
        with self.connect() as db: db.execute('INSERT INTO accounts VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET uid=excluded.uid,metadata=excluded.metadata,updated=excluded.updated',(aid,bank,self.seal(uid),self.seal(metadata),now()))
        return aid
    def accounts(self):
        with self.connect() as db: return [dict(r) for r in db.execute('SELECT id,bank,updated FROM accounts ORDER BY id')]
    def ingest(self, aid, rows, start,end,complete,error):
        with self.connect() as db:
            for r in rows: db.execute('INSERT INTO transactions VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET date=excluded.date,status=excluded.status,payload=excluded.payload',(r['id'],r['bank'],aid,r['date'],r['currency'],r['status'],self.seal(r)))
            db.execute('INSERT INTO syncs(account,start,end,fetched,complete,error,count) VALUES(?,?,?,?,?,?,?)',(aid,start,end,now(),int(complete),error,len(rows)))
    def history(self, table, limit=100):
        if table not in ('syncs','balances'): raise FinanceError('invalid_history')
        with self.connect() as db: rows=[dict(r) for r in db.execute(f'SELECT * FROM {table} ORDER BY id DESC LIMIT ?', (limit,))]
        for r in rows:
            if 'payload' in r: r['balances']=self.unseal(r.pop('payload'))
        return rows
    def snapshot(self,aid,balances):
        with self.connect() as db: db.execute('INSERT INTO balances(account,fetched,payload) VALUES(?,?,?)',(aid,now(),self.seal(balances)))
    def query(self,start,end,bank='all',account=None,currency=None,status=None,after='',limit=101):
        where=['(date BETWEEN ? AND ? OR date IS NULL)','id > ?']; args=[start,end,after]
        for col,val in [('bank',None if bank=='all' else bank),('account',account),('currency',currency),('status',status)]:
            if val is not None: where.append(col+' = ?'); args.append(val)
        with self.connect() as db: rows=db.execute('SELECT payload FROM transactions WHERE '+' AND '.join(where)+' ORDER BY id LIMIT ?',args+[limit]).fetchall()
        return [self.unseal(r[0]) for r in rows]
    def backup(self,destination):
        destination=Path(destination).resolve()
        if self.settings.root==destination or self.settings.root in destination.parents: raise FinanceError('backup_inside_repository')
        fd=os.open(destination,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600); os.close(fd)
        target=sqlite3.connect(destination)
        try:
            with self.connect() as source: source.backup(target)
        finally: target.close()
