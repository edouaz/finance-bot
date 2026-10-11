"""Validation, provider transport and normalized financial records."""
import hashlib
import json
import os
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote
import jwt
import requests

BANKS = ('bnp', 'revolut')
class FinanceError(Exception):
    """Safe error code; never contains provider payloads."""

def dates(start, end):
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        raise FinanceError('invalid_date') from None
    if a > b: raise FinanceError('invalid_date_range')
    return a, b

def money(value):
    try: d = Decimal(str(value))
    except InvalidOperation: raise FinanceError('invalid_amount') from None
    if not d.is_finite() or abs(d) > Decimal('1e15'): raise FinanceError('invalid_amount')
    return d

def safe_text(value):
    s = str(value or '')[:240]
    return re.sub(r'\b[A-Z]{2}\d{2}(?:[ ]?[A-Z0-9]){11,30}\b', '[account redacted]', s)

def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def now(): return datetime.now(timezone.utc).isoformat()

@dataclass
class Settings:
    root: Path
    storage: Path
    app_id: str
    key: Path
    sessions: Path
    @classmethod
    def load(cls):
        root = Path(__file__).resolve().parents[1]
        storage = Path(os.environ.get('FINANCE_STORAGE', str(Path.home()/'.local/share/finance-tracker'))).expanduser().resolve()
        if storage == root or root in storage.parents: raise FinanceError('storage_must_be_outside_repository')
        return cls(root, storage, os.environ.get('ENABLE_BANKING_APP_ID',''), Path(os.environ.get('ENABLE_BANKING_KEY',str(root/'keys/private.pem'))), Path(os.environ.get('FINANCE_SESSIONS',str(root/'data'))))

class Client:
    def __init__(self, settings, transport=None, sleep=time.sleep):
        self.settings, self.http, self.sleep = settings, transport or requests.Session(), sleep
    def token(self):
        if not self.settings.app_id: raise FinanceError('application_id_not_configured')
        if self.settings.key.stat().st_mode & 0o077: raise FinanceError('unsafe_key_permissions')
        t = int(time.time())
        return jwt.encode({'iss':'enablebanking.com','aud':'api.enablebanking.com','iat':t,'exp':t+600},self.settings.key.read_bytes(),algorithm='RS256',headers={'kid':self.settings.app_id})
    def get(self, path, params=None):
        for attempt in range(4):
            try:
                r = self.http.get('https://api.enablebanking.com'+path, params=params, headers={'Authorization':'Bearer '+self.token(),'Accept':'application/json'},timeout=(5,25))
            except requests.RequestException:
                if attempt == 3: raise FinanceError('network_unavailable') from None
                self.sleep(2**attempt); continue
            if r.status_code == 429 or 500 <= r.status_code < 600:
                if attempt == 3: raise FinanceError('provider_retry_exhausted')
                try: delay = float(r.headers.get('Retry-After',2**attempt))
                except ValueError: delay = 2**attempt
                self.sleep(max(0,min(delay,30))); continue
            if r.status_code in (401,403): raise FinanceError('authorization_unavailable')
            if r.status_code == 404: raise FinanceError('resource_unavailable')
            if r.status_code != 200: raise FinanceError('provider_request_rejected')
            try: data = r.json()
            except ValueError: raise FinanceError('invalid_provider_json') from None
            if not isinstance(data,dict): raise FinanceError('invalid_provider_schema')
            return data
    def session(self, bank):
        if bank not in BANKS: raise FinanceError('invalid_bank')
        p = self.settings.sessions/f'{bank}_session.json'
        if p.stat().st_mode & 0o077: raise FinanceError('unsafe_session_permissions')
        try: stored = json.loads(p.read_text()); sid=stored['session_id']
        except (ValueError,KeyError): raise FinanceError('invalid_session') from None
        info=self.get('/sessions/'+quote(sid,safe=''))
        expiry=info.get('access',{}).get('valid_until')
        if expiry:
            try: expired=datetime.fromisoformat(expiry.replace('Z','+00:00')) <= datetime.now(timezone.utc)
            except (ValueError,TypeError): raise FinanceError('invalid_session_expiry') from None
            if expired: raise FinanceError('reauthorization_required')
        if info.get('status') != 'AUTHORIZED': raise FinanceError('reauthorization_required')
        return info
    def transactions(self, uid, start=None, end=None, max_pages=100):
        if start is not None or end is not None: dates(start,end)
        rows=[]; seen=set(); params={'date_from':start,'date_to':end} if start is not None else {}
        for _ in range(max_pages):
            try:
                d=self.get('/accounts/'+quote(uid,safe='')+'/transactions',params)
                if not isinstance(d.get('transactions'),list): raise FinanceError('invalid_provider_schema')
                rows.extend(d['transactions'])
            except FinanceError as e: return rows,False,str(e)
            k=d.get('continuation_key')
            if not k: return rows,True,None
            if k in seen: return rows,False,'pagination_loop'
            seen.add(k); params['continuation_key']=k
        return rows,False,'page_limit'

def normalize(raw, bank, account):
    amt=raw.get('transaction_amount',{}); amount=money(amt.get('amount')); direction=raw.get('credit_debit_indicator')
    if direction not in ('CRDT','DBIT'): raise FinanceError('invalid_direction')
    currency=amt.get('currency','')
    if not re.fullmatch('[A-Z]{3}',currency): raise FinanceError('invalid_currency')
    signed=abs(amount) * (-1 if direction=='DBIT' else 1)
    day=raw.get('booking_date') or raw.get('transaction_date') or raw.get('value_date')
    if day: dates(day,day)
    status=raw.get('status')
    if status not in ('BOOK','PDNG'): raise FinanceError('unknown_transaction_status')
    merchant=safe_text(((raw.get('creditor') if signed<0 else raw.get('debtor')) or {}).get('name',''))
    description=safe_text(' '.join(raw.get('remittance_information') or []))
    ref=raw.get('entry_reference')
    canonical=json.dumps({k:v for k,v in raw.items() if k not in ('transaction_id','balance_after_transaction')},sort_keys=True,separators=(',',':'))
    identity='ref:'+str(ref) if ref else 'fallback:'+digest(canonical)
    return {'id':digest(bank+':'+account+':'+identity),'bank':bank,'account':account,'date':day,'amount':str(signed),'original_amount':str(amount),'currency':currency,'status':status,'merchant':merchant,'description':description,'identity_quality':'stable' if ref else 'ambiguous_fallback','raw':raw}
