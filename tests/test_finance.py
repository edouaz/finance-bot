import asyncio
import json
import os
import tempfile
import unittest
from pathlib import Path
from datetime import date
from unittest.mock import Mock,patch
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
import jwt
import requests
from finance.core import Settings, Client, FinanceError,normalize,dates,money
from finance.store import Store
from finance.service import Service
from finance.analytics import decorate,summary,recurring,alerts


def raw(ref='r1',amount='10.00',direction='DBIT',day='2026-09-01',status='BOOK',merchant='Netflix',description='subscription',currency='EUR'):
    return {'entry_reference':ref,'transaction_id':'unstable','transaction_amount':{'amount':amount,'currency':currency},'credit_debit_indicator':direction,'booking_date':day,'status':status,'creditor':{'name':merchant},'debtor':{'name':merchant},'remittance_information':[description]}

class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.base=Path(self.temp.name); self.storage=self.base/'storage'; self.storage.mkdir(mode=0o700)
        self.key=self.base/'data.key'; self.key.write_bytes(Fernet.generate_key()); self.key.chmod(0o600)
        self.env=patch.dict(os.environ,{'FINANCE_DATA_KEY':str(self.key)}); self.env.start()
        self.config=Settings(Path('/home/edouard/finance-bot'),self.storage,'test-app',self.base/'rsa.key',self.base)
        self.store=Store(self.config); self.service=Service(self.store,Mock()); self.aid=self.store.save_account('bnp','uid',{'identification_hash':'stable'})
    def tearDown(self): self.env.stop(); self.temp.cleanup()
    def rows(self,*items): return decorate([normalize(r,'bnp',self.aid) for r in items])
    def test_jwt(self):
        key=rsa.generate_private_key(public_exponent=65537,key_size=2048)
        self.config.key.write_bytes(key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption())); self.config.key.chmod(0o600)
        token=Client(self.config).token(); d=jwt.decode(token,key.public_key(),algorithms=['RS256'],audience='api.enablebanking.com',issuer='enablebanking.com')
        self.assertEqual(d['exp']-d['iat'],600); self.assertEqual(jwt.get_unverified_header(token)['kid'],'test-app')
    def test_key_permissions(self):
        self.config.key.touch(); self.config.key.chmod(0o644)
        with self.assertRaisesRegex(FinanceError,'unsafe_key'): Client(self.config).token()
    def test_pagination(self):
        c=Client(self.config); c.get=Mock(side_effect=[{'transactions':[raw()], 'continuation_key':'next'},{'transactions':[raw('r2')]}])
        rows,complete,error=c.transactions('uid','2026-09-01','2026-09-30'); self.assertEqual(len(rows),2); self.assertTrue(complete); self.assertIsNone(error)
    def test_loop_partial(self):
        c=Client(self.config); c.get=Mock(return_value={'transactions':[raw()],'continuation_key':'same'})
        rows,complete,error=c.transactions('uid','2026-09-01','2026-09-30'); self.assertFalse(complete); self.assertEqual(error,'pagination_loop'); self.assertEqual(len(rows),2)
    def test_network_partial(self):
        c=Client(self.config); c.get=Mock(side_effect=[{'transactions':[raw()],'continuation_key':'n'},FinanceError('network_unavailable')])
        self.assertEqual(c.transactions('u','2026-09-01','2026-09-30')[1:],(False,'network_unavailable'))
    def test_page_cap(self):
        c=Client(self.config); c.get=Mock(return_value={'transactions':[],'continuation_key':'n'})
        self.assertEqual(c.transactions('u','2026-09-01','2026-09-30',1)[2],'page_limit')
    def test_schema_partial(self):
        c=Client(self.config); c.get=Mock(return_value={})
        self.assertEqual(c.transactions('u','2026-09-01','2026-09-30')[2],'invalid_provider_schema')
    def test_retry_limit(self):
        transport=Mock(); response=Mock(status_code=429,headers={'Retry-After':'999'}); transport.get.return_value=response
        sleep=Mock(); c=Client(self.config,transport,sleep); c.token=Mock(return_value='fake')
        with self.assertRaisesRegex(FinanceError,'retry_exhausted'): c.get('/application')
        self.assertEqual(transport.get.call_count,4); self.assertEqual(sleep.call_count,3); self.assertEqual(sleep.call_args.args,(30,))
    def test_network_retries(self):
        transport=Mock(); transport.get.side_effect=requests.Timeout(); c=Client(self.config,transport,Mock()); c.token=Mock(return_value='fake')
        with self.assertRaisesRegex(FinanceError,'network_unavailable'): c.get('/application')
        self.assertEqual(transport.get.call_count,4)
    def test_expired_session(self):
        p=self.base/'bnp_session.json'; p.write_text(json.dumps({'session_id':'secret'})); p.chmod(0o600)
        c=Client(self.config); c.get=Mock(return_value={'status':'AUTHORIZED','access':{'valid_until':'2000-01-01T00:00:00Z'}})
        with self.assertRaisesRegex(FinanceError,'reauthorization_required'): c.session('bnp')
    def test_cancelled_session(self):
        p=self.base/'bnp_session.json'; p.write_text(json.dumps({'session_id':'secret'})); p.chmod(0o600)
        c=Client(self.config); c.get=Mock(return_value={'status':'CANCELLED'})
        with self.assertRaisesRegex(FinanceError,'reauthorization_required'): c.session('bnp')
    def test_sign_and_original(self):
        r=normalize(raw(amount='-10',direction='CRDT'),'bnp',self.aid)
        self.assertEqual(r['amount'],'10'); self.assertEqual(r['original_amount'],'-10')
    def test_unstable_transaction_id_not_identity(self):
        a=raw(); b={**a,'transaction_id':'changed'}
        self.assertEqual(normalize(a,'bnp',self.aid)['id'],normalize(b,'bnp',self.aid)['id'])
    def test_fallback_id(self):
        a=raw(None); b={**a,'transaction_id':'changed'}
        self.assertEqual(normalize(a,'bnp',self.aid)['id'],normalize(b,'bnp',self.aid)['id']); self.assertEqual(normalize(a,'bnp',self.aid)['identity_quality'],'ambiguous_fallback')
    def test_idempotent_ingest(self):
        rows=self.rows(raw()); self.store.ingest(self.aid,rows,'2026-09-01','2026-09-30',True,None); self.store.ingest(self.aid,rows,'2026-09-01','2026-09-30',True,None)
        self.assertEqual(len(self.store.query('2026-09-01','2026-09-30')),1)
    def test_account_survives_reauthorization(self):
        self.assertEqual(self.aid,self.store.save_account('bnp','new-uid',{'identification_hash':'stable'}))
        self.assertNotEqual(self.aid,self.store.save_account('revolut','uid',{'identification_hash':'stable'}))
    def test_encryption(self):
        self.store.ingest(self.aid,self.rows(raw(merchant='Sensitive Merchant')),'2026-09-01','2026-09-30',True,None)
        self.assertNotIn(b'Sensitive Merchant',self.store.path.read_bytes()); self.assertEqual(self.store.path.stat().st_mode & 0o777,0o600)
    def test_multiple_currencies(self):
        r=summary(self.rows(raw(currency='EUR'),raw('r2',currency='USD')))
        self.assertEqual(r['currencies']['EUR']['spending'],'10.00'); self.assertEqual(r['currencies']['USD']['spending'],'10.00')
    def test_refund_transfer_pending(self):
        transfer=raw('transfer',description='virement'); refund=raw('refund',direction='CRDT',description='refund'); pending=raw('pending',status='PDNG')
        r=summary(self.rows(raw(),transfer,refund,pending))
        self.assertEqual(r['currencies']['EUR']['net_spending'],'0.00'); self.assertEqual(r['pending_excluded'],1); self.assertEqual(r['currencies']['EUR']['excluded_outflows'],'10.00')
    def test_owned_transfer(self):
        t=raw(description=''); t['creditor_account']={'iban':'BE123456'}
        row=normalize(t,'bnp',self.aid); decorate([row],{'BE123456'})
        self.assertEqual(row['kind'],'internal_transfer'); self.assertEqual(row['confidence'],'confirmed'); self.assertEqual(summary([row])['currencies']['EUR']['spending'],'0')
    def test_unknown_credit_not_income(self):
        r=summary(self.rows(raw(direction='CRDT',description='gift')))
        self.assertEqual(r['currencies']['EUR']['income'],'0'); self.assertIsNone(r['currencies']['EUR']['savings_rate_estimate'])
    def test_categories(self):
        r=summary(self.rows(raw(merchant='ALDI',description='food')))
        self.assertEqual(r['currencies']['EUR']['groups']['groceries'],'10.00')
    def test_subscription_price_increase(self):
        rows=self.rows(raw('1',day='2026-07-01'),raw('2',day='2026-08-01'),raw('3',day='2026-09-01',amount='12'))
        r=recurring(rows,date(2026,9,30)); self.assertEqual(len(r),1); self.assertEqual(r[0]['price_increase_estimate'],'2.00'); self.assertEqual(r[0]['cadence'],'monthly')
    def test_two_payments_not_recurring(self): self.assertEqual(recurring(self.rows(raw(),raw('2',day='2026-08-01')),date(2026,9,30)),[])
    def test_duplicates_candidates(self): self.assertEqual(len(alerts(self.rows(raw('1'),raw('2')))['duplicate_candidates']),1)
    def test_anomaly(self):
        rows=self.rows(*[raw(str(i),amount='10',day=f'2026-09-{i+1:02}') for i in range(8)],raw('big',amount='100',day='2026-09-10'))
        self.assertEqual(len(alerts(rows)['unusual']),1)
    def test_validation(self):
        for value in ('NaN','Infinity','1e100'):
            with self.assertRaises(FinanceError): money(value)
        with self.assertRaises(FinanceError): dates('2026-10-01','2026-09-01')
        for kwargs in ({'limit':101},{'cursor':'../secret'},{'min_amount':'-1'},{'currency':'eur'},{'query':'x'*101},{'account':"' OR 1=1"}):
            with self.assertRaises(FinanceError): self.service.transactions('2026-09-01','2026-09-30',**kwargs)
    def test_search_pagination(self):
        self.store.ingest(self.aid,self.rows(*[raw(str(i)) for i in range(5)]),'2026-09-01','2026-09-30',True,None)
        first=self.service.transactions('2026-09-01','2026-09-30',limit=2); second=self.service.transactions('2026-09-01','2026-09-30',limit=2,cursor=first['next_cursor'])
        self.assertEqual(len(first['items']),2); self.assertFalse({r['id'] for r in first['items']}&{r['id'] for r in second['items']})
        self.assertNotIn('raw',first['items'][0])
    def test_partial_coverage(self):
        self.store.ingest(self.aid,[],'2026-09-01','2026-09-30',False,'page_limit')
        self.assertFalse(self.service.coverage('2026-09-01','2026-09-30')['complete'])
    def test_union_coverage(self):
        self.store.ingest(self.aid,[],'2026-09-01','2026-09-15',True,None); self.store.ingest(self.aid,[],'2026-09-16','2026-09-30',True,None)
        self.assertTrue(self.service.coverage('2026-09-01','2026-09-30','bnp')['complete'])
    def test_report(self):
        self.store.ingest(self.aid,self.rows(raw()),'2026-09-01','2026-09-30',True,None)
        r=self.service.report('2026-09-01','2026-09-30','bnp'); self.assertEqual(len(r['recommendations']),4); self.assertTrue(r['coverage']['complete']); self.assertIn('balances',r)
    def test_backup_recovery(self):
        self.store.backup(self.base/'backup.sqlite3'); self.assertEqual((self.base/'backup.sqlite3').stat().st_mode & 0o777,0o600)
        import sqlite3
        db=sqlite3.connect(self.base/'backup.sqlite3')
        try: self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        finally: db.close()
    def test_undated_retained_excluded(self):
        row=raw(); row.pop('booking_date')
        rows=self.rows(row)
        self.store.ingest(self.aid,rows,'2026-09-01','2026-09-30',False,'undated_transactions')
        self.assertEqual(len(self.store.query('2026-09-01','2026-09-30')),1)
        self.assertEqual(summary(rows)['undated_booked_excluded'],1)
        self.assertFalse(alerts(rows)['unusual'])
    def test_intelligence(self):
        from unittest.mock import patch
        import finance_mcp_v2 as server
        self.store.ingest(self.aid,self.rows(raw()),'2026-09-01','2026-09-30',True,None)
        with patch.object(server,'_service',self.service):
            result=server.get_financial_intelligence('2026-09-01','2026-09-30',budget_amount='8')
        self.assertTrue(result['budget']['over_budget'])
        self.assertEqual(result['budget']['remaining'],'-2.00')
        self.assertIsNone(result['forecast']['income_forecast'])
    def test_balance_types_not_added(self):
        import finance_mcp_v2 as server
        self.store.snapshot(self.aid,[{'balance_type':'CLBD','balance_amount':{'amount':'100','currency':'EUR'}},{'balance_type':'CLAV','balance_amount':{'amount':'90','currency':'EUR'}}])
        with patch.object(server,'_service',self.service): result=server.get_total_balance('bnp')
        self.assertEqual(result['totals_by_currency'],{'EUR':'100'})
    def test_failed_bank_sync_marks_coverage(self):
        self.store.ingest(self.aid,[],'2026-09-01','2026-09-30',True,None)
        self.service.client.session.side_effect=FinanceError('reauthorization_required')
        result=self.service.sync('bnp','2026-09-01','2026-09-30')
        self.assertFalse(result['results'][0]['complete'])
        self.assertFalse(self.service.coverage('2026-09-01','2026-09-30')['complete'])
    def test_weekly_cli_repeat_encrypted(self):
        from finance.cli import main
        out=self.base/'report.fernet'
        with patch('finance.cli.Settings.load',return_value=self.config):
            with patch('sys.argv',['finance','weekly-report','--output',str(out)]): self.assertEqual(main(),0)
            with patch('sys.argv',['finance','weekly-report','--output',str(out)]): self.assertEqual(main(),0)
        data=self.store.unseal(out.read_bytes())
        self.assertIn('recommendations',data)
        self.assertEqual(out.stat().st_mode & 0o777,0o600)
    def test_missing_bank_not_complete(self):
        self.store.ingest(self.aid,[],'2026-09-01','2026-09-30',True,None)
        result=self.service.coverage('2026-09-01','2026-09-30')
        self.assertFalse(result['complete']); self.assertEqual(result['missing_banks'],['revolut'])
    def test_all_available_provider_pagination(self):
        c=Client(self.config); c.get=Mock(return_value={'transactions':[raw()]})
        rows,complete,error=c.transactions('uid')
        self.assertTrue(complete); self.assertEqual(len(rows),1)
        self.assertEqual(c.get.call_args.args[1],{})
    def test_nullable_provider_code(self):
        t=raw(); t['bank_transaction_code']={'description':None}
        self.assertEqual(self.rows(t)[0]['kind'],'spending')
        t['bank_transaction_code']=None
        self.assertEqual(self.rows(t)[0]['category'],'subscriptions')
    def test_provider_statuses_preserved_and_excluded_from_totals(self):
        from finance.core import TRANSACTION_STATUSES
        for status in TRANSACTION_STATUSES:
            with self.subTest(status=status):
                row=self.rows(raw(status=status))[0]
                self.assertEqual(row['status'],status)
                if status!='BOOK':
                    result=summary([row])
                    self.assertEqual(result['currencies'],{})
                    self.assertEqual(result['pending_excluded'],int(status=='PDNG'))
                    self.assertEqual(result['other_statuses_excluded'],{} if status=='PDNG' else {status:1})
        with self.assertRaisesRegex(FinanceError,'unknown_transaction_status'):
            normalize(raw(status='INVALID'),'bnp',self.aid)
    def test_bnp_other_status_sync_retains_transaction(self):
        self.service.client.session.return_value={'accounts':['uid']}
        self.service.client.get.return_value={'balances':[]}
        self.service.client.transactions.return_value=([raw(status='OTHR'),raw(ref='r2')],True,None)
        result=self.service.sync('bnp','2026-09-01','2026-09-30')['results'][0]
        self.assertTrue(result['complete'])
        self.assertEqual(result['count'],2)
        self.assertIn('non_booked_status_OTHR',result['warnings'])
        rows=self.service.transactions('2026-09-01','2026-09-30',status='OTHR')['items']
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['status'],'OTHR')
    def test_discovery(self):
        from finance_mcp_v2 import mcp
        tools=asyncio.run(mcp.list_tools()); names={t.name for t in tools}
        self.assertIn('get_weekly_report',names); self.assertIn('get_transactions',names)
        self.assertIn('sync_transactions',names)
        self.assertTrue(all(t.annotations.readOnlyHint for t in tools if t.name!='sync_transactions'))
        tool=next(t for t in tools if t.name=='sync_transactions')
        self.assertFalse(tool.annotations.readOnlyHint)
        self.assertTrue(tool.annotations.openWorldHint)
    def test_mcp_sync_results_validation_and_lock(self):
        import finance_mcp_v2 as api
        from unittest.mock import patch, Mock
        fake=Mock()
        fake.sync.return_value={'results':[{'complete':False,'error':'session_expired'}]}
        with patch.object(api,'service',return_value=fake):
            result=api.sync_transactions('2026-09-01','2026-09-30','bnp')
            self.assertFalse(result['complete'])
            fake.sync.assert_called_once_with('bnp','2026-09-01','2026-09-30')
            self.assertEqual(api.sync_transactions('bad','bad')['error'],'invalid_date')
            api._sync_lock.acquire()
            try: self.assertEqual(api.sync_transactions('2026-09-01','2026-09-30')['error'],'sync_in_progress')
            finally: api._sync_lock.release()
            fake.sync.side_effect=RuntimeError('private provider detail')
            self.assertEqual(api.sync_transactions('2026-09-01','2026-09-30')['error'],'local_data_unavailable')
            self.assertFalse(api._sync_lock.locked())

if __name__=='__main__': unittest.main()
