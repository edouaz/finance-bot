"""Decimal calculations, conservative classifications and explainable estimates."""
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from statistics import median
from .core import money

CONSUMPTION={'spending','fee'}

def classify(row, owned_ibans=()):
    raw=row['raw']; text=(row['description']+' '+((raw.get('bank_transaction_code') or {}).get('description') or '')).lower()
    a=money(row['amount'])
    counterpart=(raw.get('creditor_account') if a<0 else raw.get('debtor_account')) or {}
    if counterpart.get('iban') and counterpart['iban'] in owned_ibans: return 'internal_transfer','confirmed'
    for words,kind in [(('refund','remboursement'),'refund'),(('credit card payment','paiement carte de crédit'),'credit_card_payment'),(('cash withdrawal','retrait','atm'),'cash_withdrawal'),(('savings','épargne'),'savings_transfer'),(('fee','frais'),'fee'),(('transfer','virement'),'unclassified_transfer')]:
        if any(w in text for w in words): return kind,'heuristic'
    if a>0:
        if any(w in text for w in ('salary','salaire','payroll')): return 'income','heuristic'
        return 'unclassified_credit','unknown'
    return 'spending','heuristic'

def category(row):
    text=(row['merchant']+' '+row['description']).lower()
    for words,cat in [(('aldi','lidl','delhaize','carrefour'),'groceries'),(('netflix','spotify','subscription','abonnement'),'subscriptions'),(('rent','loyer'),'housing'),(('train','sncb','uber'),'transport'),(('restaurant','café','cafe'),'dining'),(('electric','energy','internet'),'utilities')]:
        if any(w in text for w in words): return cat
    return 'uncategorized'

def decorate(rows,owned=()):
    for row in rows:
        row['kind'],row['confidence']=classify(row,owned)
        row['category']=category(row)
    # Equal amounts alone never confirm a transfer. Pair is reported for manual review.
    return rows

def public(row):
    return {k:v for k,v in row.items() if k not in ('raw',)}

def summary(rows,group='category'):
    currencies=defaultdict(lambda:{'spending':Decimal(0),'income':Decimal(0),'refunds':Decimal(0),'unclassified_credits':Decimal(0),'excluded_outflows':Decimal(0),'net_flow':Decimal(0),'groups':defaultdict(Decimal)})
    pending=0; undated=0
    for r in rows:
        if r['status']!='BOOK': pending+=1; continue
        if not r['date']: undated+=1; continue
        a=money(r['amount']); c=currencies[r['currency']]; c['net_flow']+=a
        if r['kind'] in CONSUMPTION and a<0:
            c['spending']-=a; c['groups'][str(r.get(group,'uncategorized'))]-=a
        elif r['kind']=='income' and a>0: c['income']+=a
        elif r['kind']=='refund' and a>0: c['refunds']+=a
        elif a>0 and r['kind'] not in ('internal_transfer','savings_transfer'): c['unclassified_credits']+=a
        elif a<0: c['excluded_outflows']-=a
    out={}
    for code,c in currencies.items():
        c['net_spending']=c['spending']-c['refunds']
        c['savings_rate_estimate']=str((c['income']-c['net_spending'])/c['income']) if c['income'] else None
        out[code]={k:({g:str(v) for g,v in sorted(x.items(),key=lambda p:p[1],reverse=True)[:100]} if isinstance(x,dict) else str(x) if x is not None else None) for k,x in c.items()}
    return {'currencies':out,'pending_excluded':pending,'undated_booked_excluded':undated,'classification':'Heuristic unless an owned counterparty is confirmed. Unknown credits are not income; transfer-like debits are not consumption. Savings rate is an estimate.'}

def recurring(rows,as_of):
    groups=defaultdict(list)
    for r in rows:
        if r['status']=='BOOK' and r['kind'] in CONSUMPTION and r['merchant'] and r['date']:
            groups[(r['account'],r['merchant'],r['currency'])].append(r)
    found=[]
    for (account,merchant,currency),items in groups.items():
        items=sorted(items,key=lambda r:r['date'])
        if len(items)<3: continue
        gaps=[(date.fromisoformat(b['date'])-date.fromisoformat(a['date'])).days for a,b in zip(items,items[1:])]
        interval=median(gaps)
        cadence=next((label for low,high,label in [(6,8,'weekly'),(26,33,'monthly'),(350,380,'yearly')] if low<=interval<=high),None)
        if not cadence or any(abs(g-interval)>max(3,interval*.15) for g in gaps): continue
        amounts=[abs(money(r['amount'])) for r in items]; typical=median(amounts[:-1]); last=amounts[-1]
        due=date.fromisoformat(items[-1]['date'])+timedelta(days=round(interval))
        found.append({'account':account,'merchant':merchant,'currency':currency,'cadence':cadence,'occurrences':len(items),'confidence':'medium' if len(items)<5 else 'high','evidence':{'dates':[r['date'] for r in items[-6:]],'median_gap_days':interval},'last_amount':str(last),'annual_cost_estimate':str(last*{'weekly':52,'monthly':12,'yearly':1}[cadence]),'price_increase_estimate':str(last-typical) if last>typical*Decimal('1.05') else None,'next_charge_estimate':due.isoformat(),'overdue_estimate':due<as_of,'subscription_candidate':items[-1]['category']=='subscriptions'})
    return sorted(found,key=lambda x:x['next_charge_estimate'])[:100]

def alerts(rows):
    booked=[r for r in rows if r['status']=='BOOK' and r['date']]; duplicate=[]; transfers=[]; unusual=[]
    groups=defaultdict(list)
    for r in booked: groups[(r['currency'],r['merchant'])].append(r)
    for items in groups.values():
        seen={}; negative=[abs(money(r['amount'])) for r in items if money(r['amount'])<0]
        if len(negative)>=8:
            mid=median(negative); mad=median([abs(a-mid) for a in negative])
            threshold=mid+max(Decimal(20),6*mad)
            for r in items:
                if money(r['amount'])<0 and abs(money(r['amount']))>threshold: unusual.append({'id':r['id'],'rule':'amount exceeds median + max(20 currency units, 6*MAD)','threshold':str(threshold),'confidence':'heuristic'})
        for r in items:
            key=(r['account'],r['date'],r['amount'])
            if key in seen and r['merchant']: duplicate.append({'ids':[seen[key],r['id']],'confidence':'candidate','reason':'same account, merchant, day, currency and amount; may be legitimate'})
            seen[key]=r['id']
    amounts=defaultdict(list)
    for r in booked: amounts[(r['currency'],abs(money(r['amount'])))].append(r)
    for items in amounts.values():
        if len(items)>100: continue
        for i,a in enumerate(items):
            for b in items[i+1:]:
                if a['account']!=b['account'] and money(a['amount'])==-money(b['amount']) and abs((date.fromisoformat(a['date'])-date.fromisoformat(b['date'])).days)<=3:
                    transfers.append({'ids':[a['id'],b['id']],'confidence':'candidate','excluded_from_spending':a['kind']=='internal_transfer' and b['kind']=='internal_transfer','reason':'opposite amounts across accounts within 3 days; verify counterparties'})
    return {'unusual':unusual[:100],'duplicate_candidates':duplicate[:100],'transfer_candidates':transfers[:100]}
