"""Read-only cached MCP tools. Synchronization is a separate operator command."""
import functools
import threading
import time
from datetime import date, timedelta
from typing import Literal
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations
from finance.core import Settings, Client, FinanceError, dates, money
from finance.store import Store
from finance.service import Service
from finance.analytics import summary, recurring, alerts, public

mcp=FastMCP('Personal Finance Tracker v2')
annotations=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)
_service=None
_lock=threading.Lock()
_calls=[]

def service():
    global _service
    if _service is None:
        with _lock:
            if _service is None:
                config=Settings.load(); _service=Service(Store(config),Client(config))
    return _service

def guarded(fn):
    @functools.wraps(fn)
    def run(*args,**kwargs):
        with _lock:
            t=time.monotonic(); _calls[:]=[x for x in _calls if t-x<60]
            if len(_calls)>=60: return {'error':'local_rate_limit','retry_after_seconds':60}
            _calls.append(t)
        try:
            import json
            result=fn(*args,**kwargs)
            if len(json.dumps(result,ensure_ascii=False).encode())>98304: return {'error':'response_limit_narrow_date_range_or_filters'}
            return result
        except FinanceError as e: return {'error':str(e)}
        except Exception: return {'error':'local_data_unavailable'}
    return run

Bank=Literal['all','bnp','revolut']

@mcp.tool(annotations=annotations)
@guarded
def get_connection_status() -> dict:
    """Cached consent expirations and local configuration status; does not contact banks."""
    import json
    from datetime import datetime,timezone
    settings=Settings.load(); result={}
    for bank in ('bnp','revolut'):
        try:
            data=json.loads((settings.sessions/f'{bank}_session.json').read_text()); expiry=data.get('access',{}).get('valid_until')
            expired=datetime.fromisoformat(expiry.replace('Z','+00:00'))<=datetime.now(timezone.utc) if expiry else None
            result[bank]={'valid_until':expiry,'reauthorization_required':expired,'live_verified':False}
        except Exception: result[bank]={'status':'session_unavailable','live_verified':False}
    return result

@mcp.tool(annotations=annotations)
@guarded
def get_accounts(bank: Bank='all') -> dict:
    """List opaque local account references and latest metadata fetch times; no IBANs."""
    return {'accounts':[a for a in service().store.accounts() if bank=='all' or a['bank']==bank]}

@mcp.tool(annotations=annotations)
@guarded
def get_balances(bank: Bank='all',account: str|None=None,history: bool=False) -> dict:
    """Latest cached balances or at most 100 historical snapshots; balance types may overlap."""
    return service().balances(bank,account,history)

@mcp.tool(annotations=annotations)
@guarded
def get_total_balance(bank: Bank='all',balance_type: str='CLBD') -> dict:
    """Total one explicitly selected balance type per account, separately per currency."""
    totals={}; included=[]; missing=[]
    data=service().balances(bank)
    for account in service().store.accounts():
        if bank!='all' and account['bank']!=bank: continue
        snapshot=next((s for s in data['snapshots'] if s['account']==account['id']),None)
        matches=[b for b in snapshot['balances'] if b['type']==balance_type] if snapshot else []
        if len(matches)!=1: missing.append(account['id']); continue
        b=matches[0]; c=b['currency']; totals[c]=totals.get(c,money(0))+money(b['amount']); included.append(account['id'])
    return {'totals_by_currency':{k:str(v) for k,v in totals.items()},'balance_type':balance_type,'included_accounts':included,'missing_or_ambiguous_accounts':missing,'complete':bool(included) and not missing,'warning':'Cached balances; inspect fetched timestamps with get_balances.'}

@mcp.tool(annotations=annotations)
@guarded
def get_data_coverage(start_date: str,end_date: str,bank: Bank='all',account: str|None=None) -> dict:
    """Coverage intervals, latest synchronization state and freshness warnings."""
    return service().coverage(start_date,end_date,bank,account)

@mcp.tool(annotations=annotations)
@guarded
def get_sync_status() -> dict:
    """Last 100 local synchronization attempts; no bank requests or mutations."""
    return {'syncs':service().store.history('syncs')}

@mcp.tool(annotations=annotations)
@guarded
def get_transactions(start_date: str,end_date: str,bank: Bank='all',account: str|None=None,currency: str|None=None,status: Literal['BOOK','PDNG']|None=None,query: str='',direction: Literal['all','incoming','outgoing']='all',category: str|None=None,kind: str|None=None,min_amount: str|None=None,max_amount: str|None=None,limit: int=50,cursor: str|None=None,transaction_id: str|None=None) -> dict:
    """Search cached history; 1–100 records/page, absolute amount filters. Reuse identical filters with next_cursor. Refund/pending/detail views use kind/status/transaction_id."""
    return service().transactions(start_date,end_date,bank,account,currency,status,query,direction,category,kind,min_amount,max_amount,limit,cursor,transaction_id)

@mcp.tool(annotations=annotations)
@guarded
def get_recent_transactions(last_n_days: int=7,bank: Bank='all',limit: int=50,cursor: str|None=None) -> dict:
    """Recent cached transactions, with bounded pagination and missing-data warnings."""
    if not 1<=last_n_days<=3660: raise FinanceError('invalid_days')
    end=date.today(); start=end-timedelta(days=last_n_days-1)
    return service().transactions(start.isoformat(),end.isoformat(),bank,limit=limit,cursor=cursor)

@mcp.tool(annotations=annotations)
@guarded
def get_spending_summary(start_date: str,end_date: str,bank: Bank='all',account: str|None=None,group_by: Literal['category','merchant','date','month']='category') -> dict:
    """Consumption, refunds, income estimates and cashflow by currency; pending excluded. Group by category, merchant, day or month; maximum 20,000 source records."""
    rows=service().analysis_rows(start_date,end_date,bank,account)
    if group_by=='month':
        for r in rows: r['month']=r['date'][:7] if r['date'] else 'undated'
    result=summary(rows,group_by); days=(dates(start_date,end_date)[1]-dates(start_date,end_date)[0]).days+1
    for c in result['currencies'].values(): c['average_daily_spending']=str(money(c['spending'])/days)
    result['coverage']=service().coverage(start_date,end_date,bank,account)
    return result

@mcp.tool(annotations=annotations)
@guarded
def compare_periods(start_date: str,end_date: str,previous_start: str,previous_end: str,bank: Bank='all') -> dict:
    """Compare per-currency consumption across explicit periods; lengths included for interpretation."""
    current=get_spending_summary(start_date,end_date,bank); previous=get_spending_summary(previous_start,previous_end,bank)
    if 'error' in current or 'error' in previous: raise FinanceError('comparison_unavailable')
    changes={}
    for c in set(current['currencies'])|set(previous['currencies']):
        a=money(current['currencies'].get(c,{}).get('spending','0')); b=money(previous['currencies'].get(c,{}).get('spending','0'))
        changes[c]={'absolute_change':str(a-b),'relative_change':str((a-b)/b) if b else None}
    return {'current':current,'previous':previous,'changes':changes,'days':[(dates(a,b)[1]-dates(a,b)[0]).days+1 for a,b in [(start_date,end_date),(previous_start,previous_end)]]}

@mcp.tool(annotations=annotations)
@guarded
def get_recurring_payments(start_date: str,end_date: str,bank: Bank='all',subscriptions_only: bool=False) -> dict:
    """Recurring candidates with cadence evidence, confidence, annual costs, upcoming estimates and possible price increases; at least three booked occurrences."""
    rows=service().analysis_rows(start_date,end_date,bank); found=recurring(rows,dates(start_date,end_date)[1])
    return {'candidates':[r for r in found if not subscriptions_only or r['subscription_candidate']],'coverage':service().coverage(start_date,end_date,bank),'warning':'Recurrence is heuristic; next charges and annual costs are estimates. Use a long history window.'}

@mcp.tool(annotations=annotations)
@guarded
def get_financial_alerts(start_date: str,end_date: str,bank: Bank='all') -> dict:
    """Explainable unusual-spending, duplicate-payment and internal-transfer candidates; each list capped at 100."""
    return {**alerts(service().analysis_rows(start_date,end_date,bank)),'coverage':service().coverage(start_date,end_date,bank)}

@mcp.tool(annotations=annotations)
@guarded
def get_financial_report(start_date: str,end_date: str,bank: Bank='all') -> dict:
    """Date-range dashboard/report: totals, largest transactions, recurring estimates, alerts, balances, coverage and review recommendations."""
    return service().report(start_date,end_date,bank)

@mcp.tool(annotations=annotations)
@guarded
def get_weekly_report() -> dict:
    """Previous seven completed calendar days in Europe/Brussels, with extended recurring history."""
    from zoneinfo import ZoneInfo
    from datetime import datetime
    end=datetime.now(ZoneInfo('Europe/Brussels')).date()-timedelta(days=1); start=end-timedelta(days=6)
    result=service().report(start.isoformat(),end.isoformat())
    result['recurring']=get_recurring_payments((end-timedelta(days=365)).isoformat(),end.isoformat())
    return result

@mcp.tool(annotations=annotations)
@guarded
def get_financial_intelligence(start_date: str,end_date: str,bank: Bank='all',currency: str='EUR',budget_amount: str|None=None,category: str|None=None,forecast_days: int=30) -> dict:
    """Budget against an explicit user-supplied amount, estimated fixed/variable consumption, recurring-charge forecast and review opportunities; no automatic budget or income assumptions."""
    import re
    from datetime import datetime
    from zoneinfo import ZoneInfo
    if not re.fullmatch('[A-Z]{3}',currency): raise FinanceError('invalid_currency')
    if not 1<=forecast_days<=366: raise FinanceError('invalid_forecast_days')
    budget=money(budget_amount) if budget_amount is not None else None
    if budget is not None and budget<0: raise FinanceError('invalid_budget')
    rows=service().analysis_rows(start_date,end_date,bank)
    selected=[r for r in rows if r['currency']==currency and (not category or r['category']==category)]
    today=datetime.now(ZoneInfo('Europe/Brussels')).date()
    candidates=recurring(selected,today)
    keys={(r['account'],r['merchant'],r['currency']) for r in candidates}
    consumption=[r for r in selected if r['status']=='BOOK' and r['date'] and r['kind'] in ('spending','fee') and money(r['amount'])<0]
    spent=sum((-money(r['amount']) for r in consumption),money(0))
    fixed=sum((-money(r['amount']) for r in consumption if (r['account'],r['merchant'],r['currency']) in keys),money(0))
    obligations=[]
    for r in candidates:
        due=date.fromisoformat(r['next_charge_estimate']); interval={'weekly':7,'monthly':30,'yearly':365}[r['cadence']]
        if due<today: continue
        while due<=today+timedelta(days=forecast_days):
            obligations.append({'merchant':r['merchant'],'date_estimate':due.isoformat(),'amount_estimate':r['last_amount']})
            due+=timedelta(days=interval)
    return {'currency':currency,'spending':str(spent),'fixed_spending_estimate':str(fixed),'variable_spending_estimate':str(spent-fixed),'budget':{'amount':str(budget),'remaining':str(budget-spent),'over_budget':spent>budget} if budget is not None else {'status':'not_configured'},'forecast':{'days':forecast_days,'recurring_outflow_estimate':str(sum((money(r['amount_estimate']) for r in obligations),money(0))),'obligations':obligations[:100],'truncated':len(obligations)>100,'income_forecast':None},'savings_opportunities':[{'merchant':r['merchant'],'annual_cost_estimate':r['annual_cost_estimate'],'action':'Review whether this recurring service is still needed.'} for r in candidates if r['subscription_candidate']][:20],'coverage':service().coverage(start_date,end_date,bank),'warning':'Fixed/variable classification and future charges are heuristic. Monthly dates use a 30-day interval. Overdue candidates are excluded. Income and savings-account changes are not inferred.'}

if __name__=='__main__': mcp.run(transport='stdio')
