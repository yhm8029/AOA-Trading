"""Synthetic-only accounting and import regressions; no private trader records."""
import csv,io,json,tempfile,unittest,zipfile
from pathlib import Path
from aoa.performance_ledger import result_metrics,summary_row,PnlStore
from aoa.performance_import import import_file
from aoa.model import adapt_order,present_order
from aoa.store import Store


def orders():
    data=[]
    for oid,role,stamp,qty,px,before,after in [
      ('a','Entry','2021-01-01T00:00:00Z',100,100,0,100),
      ('b','Entry','2021-01-01T00:01:00Z',200,200,100,300),
      ('c','Exit','2021-01-01T00:05:00Z',300,300,300,0)]:
        data.append(present_order(adapt_order(dict(ep_id='SYNTH',symbol='XBTUSD',direction='Long',role=role,orderid=oid,first=stamp,last=stamp,qty=qty,first_price=px,vwap=px,inverse_vwap=px,q_before=before,q_after=after))))
    return data


def ledger():
    return summary_row({'ID':'SYNTH','계약':'XBTUSD','방향':'롱','최초 진입시각':'2021-01-01T00:00:00Z','최종 청산시각':'2021-01-01T00:05:00Z',
        '누적 진입수량':300,'누적 청산수량':300,'가격손익(BTC)':1,'거래수수료(BTC)':.01,'펀딩비(BTC)':.02,'최종 순손익(BTC)':.97})

class PerformanceTests(unittest.TestCase):
    def test_inverse_denominator_and_net(self):
        p=result_metrics(orders(),[ledger()])
        self.assertAlmostEqual(p['entry_value_btc'],2)
        self.assertAlmostEqual(p['net_return_pct'],48.5)
        self.assertEqual(p['return_quality'],'ledger_and_denominator_verified')
        self.assertTrue(p['position_closed']);self.assertTrue(p['ledger_verified'])
        self.assertIsNone(p['reference_roi_pct'])

    def test_partial_turnover_no_whole_return(self):
        p=result_metrics(orders()[1:],[ledger()])
        self.assertIsNone(p['net_return_pct']);self.assertIsNone(p['net_return_estimate_pct'])
        self.assertEqual(p['net_pnl_btc'],.97)

    def test_average_fallback_is_labeled_not_exact(self):
        ev=orders()
        for e in ev:e['inverse_price']=None
        p=result_metrics(ev,[ledger()]);self.assertIsNone(p['net_return_pct']);self.assertAlmostEqual(p['net_return_estimate_pct'],48.5)

    def test_unknown_cost_does_not_become_zero(self):
        l=ledger();l.update(trade_fee_btc=None,funding_fee_btc=None)
        p=result_metrics(orders(),[l]);self.assertIsNone(p['trade_fee_btc']);self.assertEqual(p['net_pnl_btc'],.97)

    def test_conflict_and_symbol_mismatch(self):
        a=ledger();b=dict(a,net_pnl_btc=.98)
        self.assertTrue(result_metrics(orders(),[a,b])['pnl_conflict'])
        self.assertIsNone(result_metrics(orders(),[dict(a,symbol='ETHUSD')])['net_pnl_btc'])

    def test_reported_net_conflict(self):
        ev=orders();ev[0]['episode_pnl_btc']=12
        self.assertTrue(result_metrics(ev,[ledger()])['pnl_conflict'])

    def test_no_implicit_multiplier_for_other_contract(self):
        ev=orders()
        for e in ev:e['symbol']='ETHUSD'
        l=ledger();l['symbol']='ETHUSD'
        self.assertIsNone(result_metrics(ev,[l])['net_return_pct'])

    def test_zero_and_rebate(self):
        l=ledger();l.update(net_pnl_btc=0,gross_pnl_btc=.01,trade_fee_btc=-.01,funding_fee_btc=.02)
        self.assertEqual(result_metrics(orders(),[l])['net_return_pct'],0)
        self.assertAlmostEqual(result_metrics(orders(),[ledger()],.5)['reference_roi_pct'],194)

    def test_open_position_hidden(self):
        ev=orders()[:2];ev[0]['episode_pnl_btc']=1
        p=result_metrics(ev);self.assertFalse(p['position_closed']);self.assertIsNone(p['net_return_estimate_pct'])

    def test_reentry_is_counted_again(self):
        ev=orders();ev[1]['inverse_price']=100;ev[1]['avg_price']=100
        l=ledger();p=result_metrics(ev,[l]);self.assertAlmostEqual(p['entry_value_btc'],3)

    def test_explicit_summary_denominator(self):
        l=ledger();l['entry_value_btc']=2
        self.assertEqual(result_metrics(orders()[:1],[l])['net_return_pct'],48.5)

    def test_unsafe_identity(self):
        l=ledger();l['start_us']+=100_000_000
        self.assertTrue(result_metrics(orders(),[l])['pnl_conflict'])

    def test_bad_equation_rejected(self):
        with self.assertRaises(ValueError):
            summary_row({'ID':'A','계약':'XBTUSD','최종 순손익(BTC)':9,'가격손익(BTC)':1,'거래수수료(BTC)':.1,'펀딩비(BTC)':0})

    def test_csv_metadata_reimport_legacy_digest(self):
        with tempfile.TemporaryDirectory() as td:
            s=PnlStore(Path(td)/'data');p=Path(td)/'bundle.zip'
            l=ledger();headers=['episode_id','symbol','direction','start','end','entry_qty','exit_qty','net_pnl_btc','entry_value_btc']
            text=io.StringIO();w=csv.writer(text);w.writerow(headers);w.writerow(['SYNTH','XBTUSD','Long','2021-01-01T00:00:00Z','2021-01-01T00:05:00Z',300,300,.97,2])
            with zipfile.ZipFile(p,'w') as z:z.writestr('source_metadata/input/episodes.csv',text.getvalue())
            from aoa.importer import sha256
            with s.connect() as db:db.execute('INSERT INTO imports(sha256,name,report) VALUES(?,?,?)',(sha256(p),'old', '{}'))
            r=import_file(s,p);self.assertEqual(r['counts']['position_summaries'],1)
            self.assertEqual(s.performance('SYNTH')['net_return_pct'],48.5)
            self.assertTrue(import_file(s,p)['already_imported'])

    def test_xlsx_cached_values_only(self):
        from xml.sax.saxutils import escape
        with tempfile.TemporaryDirectory() as td:
            s=PnlStore(Path(td)/'data');p=Path(td)/'report.xlsx'
            headers=['ID','계약','방향','최초 진입시각','최종 청산시각','누적 진입수량','누적 청산수량','최종 순손익(BTC)','누적 진입계약가치(BTC)']
            rows=[]
            for ri,values in [(4,headers),(5,['SYNTH','XBTUSD','Long','2021-01-01T00:00:00Z','2021-01-01T00:05:00Z',300,300,.97,2])]:
                cells=[]
                for ci,v in enumerate(values):
                    ref=chr(65+ci)+str(ri)
                    cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>')
                rows.append('<row>'+''.join(cells)+'</row>')
            with zipfile.ZipFile(p,'w') as z:
                z.writestr('xl/workbook.xml','<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"/>')
                z.writestr('xl/worksheets/sheet1.xml','<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'+''.join(rows)+'</sheetData></worksheet>')
            r=import_file(s,p);self.assertEqual(r['counts']['position_summaries'],1)
            self.assertEqual(s.performance('SYNTH')['net_return_pct'],48.5)

if __name__=='__main__':unittest.main()
