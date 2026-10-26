import re
from datetime import date, datetime, timezone
from urllib.parse import quote
from .core import BANKS, TRANSACTION_STATUSES, FinanceError, dates, money, normalize, now
from .analytics import decorate, public, summary, recurring, alerts

class Service:
    def __init__(self,store,client): self.store,self.client=store,client
    def sync(self,bank,start,end):
        dates(start,end)
        if bank not in (*BANKS,'all'): raise FinanceError('invalid_bank')
        result=[]
        for b in BANKS if bank=='all' else (bank,):
            try: session=self.client.session(b)
            except (FinanceError,OSError) as e:
                error=str(e) if isinstance(e,FinanceError) else 'session_file_unavailable'
                for cached in self.store.accounts():
                    if cached['bank']==b: self.store.ingest(cached['id'],[],start,end,False,error)
                result.append({'bank':b,'complete':False,'error':error}); continue
            metadata={a['uid']:a for a in session.get('accounts_data',[])}
            for uid in session.get('accounts',[]):
                aid=self.store.save_account(b,uid,metadata.get(uid,{'uid':uid}))
                warnings=[]
                try:
                    detail=self.client.get('/accounts/'+quote(uid,safe='')+'/details')
                    self.store.save_account(b,uid,{**metadata.get(uid,{'uid':uid}),**detail})
                except FinanceError: warnings.append('account_details_unavailable')
                try:
                    balances=self.client.get('/accounts/'+quote(uid,safe='')+'/balances')
                    if not isinstance(balances.get('balances'),list): raise FinanceError('invalid_balance_schema')
                    self.store.snapshot(aid,balances['balances'])
                except FinanceError: warnings.append('balances_unavailable')
                raw,complete,error=self.client.transactions(uid,start,end); rows=[]; identities={}
                for t in raw:
                    try:
                        row=normalize(t,b,aid)
                        if not row['date']: complete=False; error='undated_transactions'
                        if row['status'] not in ('BOOK','PDNG'): warnings.append('non_booked_status_'+row['status'])
                        # Preserve same-page multiplicity where no stable ID exists.
                        if row['identity_quality']=='ambiguous_fallback':
                            from .core import digest
                            n=identities.get(row['id'],0); identities[row['id']]=n+1
                            row['id']=digest(row['id']+':'+str(n)); warnings.append('ambiguous_fallback_identity')
                        rows.append(row)
                    except (FinanceError,AttributeError,TypeError): complete=False; error='invalid_transaction_schema'
                self.store.ingest(aid,rows,start,end,complete,error)
                result.append({'bank':b,'account':aid,'count':len(rows),'complete':complete,'error':error,'warnings':sorted(set(warnings))})
        return {'results':result,'fetched_at':now()}
    def owned_ibans(self):
        with self.store.connect() as db:
            info=[self.store.unseal(r[0]) for r in db.execute('SELECT metadata FROM accounts')]
        return {d.get('account_id',{}).get('iban') for d in info if d.get('account_id',{}).get('iban')}
    def coverage(self,start,end,bank='all',account=None):
        a,b=dates(start,end)
        if bank not in (*BANKS,'all'): raise FinanceError('invalid_bank')
        if account and not re.fullmatch('[a-f0-9]{24}',account): raise FinanceError('invalid_account')
        accounts=[x for x in self.store.accounts() if (bank=='all' or x['bank']==bank) and (not account or x['id']==account)]
        statuses=[]
        with self.store.connect() as db:
            for item in accounts:
                runs=[dict(r) for r in db.execute('SELECT * FROM syncs WHERE account=? ORDER BY id DESC LIMIT 1000',(item['id'],))]
                intervals=sorted((date.fromisoformat(r['start']),date.fromisoformat(r['end'])) for r in runs if r['complete'])
                position=a
                from datetime import timedelta
                for lo,hi in intervals:
                    if lo<=position<=hi: position=hi+timedelta(days=1)
                fresh=bool(runs) and (datetime.now(timezone.utc)-datetime.fromisoformat(runs[0]['fetched'])).total_seconds()<86400
                statuses.append({'account':item['id'],'bank':item['bank'],'requested_range_fetched':position>b,'fresh':fresh,'latest_sync':runs[0] if runs else None})
        expected=set(BANKS) if bank=='all' and not account else {bank} if bank!='all' else set()
        missing=sorted(expected-{s['bank'] for s in statuses})
        return {'accounts':statuses,'missing_banks':missing,'complete':bool(statuses) and not missing and all(s['requested_range_fetched'] and s['fresh'] and s['latest_sync']['complete'] for s in statuses),'warning':'Provider date limits, pending changes, and upstream omissions cannot be ruled out. Fetched coverage is not proof of full bank history.'}
    def transactions(self,start,end,bank='all',account=None,currency=None,status=None,query='',direction='all',category=None,kind=None,min_amount=None,max_amount=None,limit=50,cursor=None,transaction_id=None):
        dates(start,end)
        if bank not in (*BANKS,'all'): raise FinanceError('invalid_bank')
        if not 1<=limit<=100: raise FinanceError('invalid_limit')
        if direction not in ('all','incoming','outgoing'): raise FinanceError('invalid_direction')
        if status is not None and status not in TRANSACTION_STATUSES: raise FinanceError('invalid_status')
        if currency and not re.fullmatch('[A-Z]{3}',currency): raise FinanceError('invalid_currency')
        if len(query)>100: raise FinanceError('query_too_long')
        if cursor and not re.fullmatch('[a-f0-9]{64}',cursor): raise FinanceError('invalid_cursor')
        if transaction_id and not re.fullmatch('[a-f0-9]{64}',transaction_id): raise FinanceError('invalid_transaction_id')
        if account and not re.fullmatch('[a-f0-9]{24}',account): raise FinanceError('invalid_account')
        low=money(min_amount) if min_amount is not None else None; high=money(max_amount) if max_amount is not None else None
        if low is not None and (low<0 or high is not None and high<low): raise FinanceError('invalid_amount_range')
        if high is not None and high<0: raise FinanceError('invalid_amount_range')
        rows=decorate(self.store.query(start,end,bank,account,currency,status,cursor or '',limit=1001),self.owned_ibans())
        out=[]; scanned=''
        for r in rows[:1000]:
            scanned=r['id']; amount=money(r['amount'])
            if transaction_id and r['id']!=transaction_id: continue
            if query.lower() not in (r['merchant']+' '+r['description']).lower(): continue
            if direction=='outgoing' and amount>=0 or direction=='incoming' and amount<=0: continue
            if category and r['category']!=category or kind and r['kind']!=kind: continue
            if low is not None and abs(amount)<low or high is not None and abs(amount)>high: continue
            out.append(public(r))
            if len(out)==limit: break
        more=bool(scanned) and (scanned!=rows[-1]['id'] or len(rows)>1000)
        return {'items':out,'next_cursor':scanned if more else None,'coverage':self.coverage(start,end,bank,account),'ordering':'opaque id ascending','warning':'Undated records are included regardless of date range. Fallback identities can merge or duplicate records across changed provider representations.'}
    def analysis_rows(self,start,end,bank='all',account=None):
        dates(start,end)
        if bank not in (*BANKS,'all'): raise FinanceError('invalid_bank')
        if account and not re.fullmatch('[a-f0-9]{24}',account): raise FinanceError('invalid_account')
        rows=self.store.query(start,end,bank,account,limit=20001)
        if len(rows)>20000: raise FinanceError('analysis_limit_narrow_date_range')
        return decorate(rows,self.owned_ibans())
    def report(self,start,end,bank='all',account=None):
        rows=self.analysis_rows(start,end,bank,account); a,b=dates(start,end)
        totals=summary(rows); rec=recurring(rows,b); detected=alerts(rows)
        largest=sorted([r for r in rows if r['status']=='BOOK' and money(r['amount'])<0],key=lambda r:abs(money(r['amount'])),reverse=True)[:10]
        recommendations=['Check coverage and renew any expired bank consent before relying on totals.','Review uncategorized transfers and credits to improve consumption and income estimates.','Verify recurring candidates and price changes against merchant invoices.','Review duplicate and unusual candidates before taking action.']
        return {'start':start,'end':end,'summary':totals,'largest_transactions':[public(r) for r in largest],'recurring':rec,'alerts':detected,'balances':self.balances(bank,account),'coverage':self.coverage(start,end,bank,account),'recommendations':recommendations,'recommendations_basis':'General review checklist; no paid model calls or investment advice.','limitations':['No configured budgets','Savings balance changes require explicitly identified savings accounts','Forecasts are recurring-charge estimates, not guaranteed obligations']}
    def balances(self,bank='all',account=None,history=False):
        if bank not in (*BANKS,'all'): raise FinanceError('invalid_bank')
        accounts={a['id']:a for a in self.store.accounts() if (bank=='all' or a['bank']==bank) and (not account or a['id']==account)}
        seen=set(); output=[]
        for r in self.store.history('balances',100):
            if r['account'] not in accounts or not history and r['account'] in seen: continue
            seen.add(r['account']); clean=[]
            for balance in r['balances']:
                amt=balance.get('balance_amount',{})
                clean.append({'type':balance.get('balance_type'),'amount':str(money(amt.get('amount'))),'currency':amt.get('currency'),'reference_date':balance.get('reference_date')})
            output.append({'account':r['account'],'bank':accounts[r['account']]['bank'],'fetched':r['fetched'],'balances':clean})
        return {'snapshots':output,'warning':'Different balance types overlap; do not add them. Currencies are never converted.'}
