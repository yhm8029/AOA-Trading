"""Research engine regression tests. Synthetic orders only, not AOA validation."""
import copy
import json
import tempfile
import unittest
from aoa.study import StudyStore, closed_context, with_imported_context, explain_event
from aoa.model import adapt_order, time_us
from aoa.store import Store

T=1609675200

def event(role='Entry',before=0,after=17000,px=100,qty=17000,minute=0):
    raw={'ep_id':'SYNTHETIC','orderid':f'SYNTHETIC-{role}-{minute}', 'role':role,'direction':'Long','symbol':'XBTUSD',
         'qty':qty,'event_time_assumed_utc':__import__('datetime').datetime.fromtimestamp(T+minute*60,__import__('datetime').timezone.utc).isoformat(),
         'execution_price':px,'qty_before':before,'qty_after':after,'avg_basis_before':100}
    e=adapt_order(raw);e['last_observed']=True;return e


def rows(count=2881):
    return [(T-(count-i)*60,100+i*.001,100.2+i*.001,99.8+i*.001,100.05+i*.001,10) for i in range(count)]

class ContextTests(unittest.TestCase):
    def test_all_six_horizons_complete(self):
        c=closed_context(rows(),T*1_000_000)
        self.assertEqual(c['valid_1m'],1440)
        self.assertEqual([x['minutes'] for x in c['frames']],[1,5,15,60,240,1440])
        self.assertTrue(all(x['available'] for x in c['frames']))
        self.assertEqual(c['last_candle']['relative_volume20'],1)
        self.assertEqual(c['frames'][4]['structure'],'상승 구조')
    def test_future_and_event_minute_cannot_change_context(self):
        history=rows();c=closed_context(history,T*1_000_000+55_000_000)
        poisoned=history+[(T,1,999999,.01,800000,999999999),(T+60,9,10,1,2,1000)]
        self.assertEqual(c,closed_context(poisoned,T*1_000_000+55_000_000))
    def test_missing_previous_minute_is_not_zero(self):
        c=closed_context(rows()[:-1],T*1_000_000)
        self.assertIsNone(c['last_candle'])
        self.assertTrue(all(x['return_pct'] is None and not x['available'] for x in c['frames']))
    def test_imported_snapshot_must_match_first_endpoint(self):
        e=event();e['features']={'pre_last_open_utc':'1999-01-01T00:00:00Z','pre_return_5m_pct':123}
        c=with_imported_context(closed_context([],e['first_us']),e)
        self.assertIsNone(c['frames'][1]['return_pct'])
        from datetime import datetime,timezone
        e['features']['pre_last_open_utc']=datetime.fromtimestamp(T-60,timezone.utc).isoformat()
        c=with_imported_context(closed_context([],e['first_us']),e)
        self.assertEqual(c['frames'][1]['return_pct'],123)
        self.assertEqual(c['frames'][1]['source'],'supplied_first_endpoint_pre_features')
        self.assertFalse(c['frames'][1]['available'])

class ExplanationTests(unittest.TestCase):
    def test_unknown_before_is_not_confirmed_entry(self):
        e=event(before=None);r=explain_event(e,[],closed_context([],e['first_us']))
        self.assertEqual(r['action'],'INCREASE')
        self.assertTrue(r['limitations']);self.assertTrue(r['not_a_signal'])
        self.assertFalse(r['hypotheses'])
    def test_add_uses_first_price_not_group_future_average(self):
        e=event(before=17000,after=34000,px=99);e['last_us']+=3600*1_000_000;e['avg_price']=9999
        context=closed_context(rows(),e['first_us'])
        r=explain_event(e,[],context,T+60)
        self.assertEqual(r['action'],'ADD');self.assertAlmostEqual(r['reference_price_change_pct'],-1)
        self.assertFalse(r['quantity_disclosed'])
        # Compare structured outputs, not a substring that can occur in float decimals.
        poison=copy.deepcopy(e);poison['avg_price']=12345678;poison['qty']=987654321;poison['position_after']=76543210
        self.assertEqual(r,explain_event(poison,[],context,T+60))
        self.assertNotIn('avg_price',r)
    def test_direction_and_profit_not_inferred_from_exit_alone(self):
        e=event('Exit',before=17000,after=10000,px=99,qty=7000)
        r=explain_event(e,[],closed_context(rows(),e['first_us']))
        self.assertEqual(r['action'],'LOSS_REDUCE')
        e['direction']='Short';r=explain_event(e,[],closed_context(rows(),e['first_us']))
        self.assertEqual(r['action'],'TP')
        e['basis_before']=None;r=explain_event(e,[],closed_context([],e['first_us']))
        self.assertEqual(r['action'],'REDUCE')
    def test_future_pnl_and_post_columns_never_used(self):
        e=event();context=closed_context(rows(),e['first_us']);base=explain_event(e,[],context,T+60)
        poison=copy.deepcopy(e);poison.update(episode_pnl_btc=987654321,legacy_label='WIN-SUPER-HIGH-CONFIDENCE')
        poison['features']={'post_proxy_15m_return_pct':88888888}
        self.assertEqual(base,explain_event(poison,[],context,T+60))
    def test_equal_quantity_alone_does_not_create_tactical_cut(self):
        p=event(before=None,after=None,minute=-10);e=event('Exit',before=None,after=None,minute=0)
        r=explain_event(e,[p],closed_context(rows(),e['first_us']))
        self.assertNotIn('tactical_unwind',[h['code'] for h in r['hypotheses']])
    def test_tactical_requires_nonoverlap_and_consistent_endpoints(self):
        p=event(before=10000,after=27000,minute=-10);e=event('Exit',before=27000,after=10000)
        r=explain_event(e,[p],closed_context(rows(),e['first_us']))
        self.assertIn('tactical_unwind',[h['code'] for h in r['hypotheses']])
        p['last_us']=e['first_us']+1
        r=explain_event(e,[p],closed_context(rows(),e['first_us']))
        self.assertNotIn('tactical_unwind',[h['code'] for h in r['hypotheses']])
    def test_replay_cannot_claim_full_close_before_last_fill(self):
        e=event('Exit',before=17000,after=0,px=101);e['last_us']+=600*1_000_000
        r=explain_event(e,[],closed_context(rows(),e['first_us']),T+60)
        self.assertEqual(r['action'],'TP');self.assertFalse(r['quantity_disclosed'])
    def test_small_initial_order_is_not_skipped_for_a_million_add(self):
        with tempfile.TemporaryDirectory() as d:
            s=StudyStore(d)
            with s.connect() as db:
                Store.order(db,event(qty=17,after=17),'SYNTHETIC')
                Store.order(db,event(qty=2000000,before=17,after=2000017,minute=60),'SYNTHETIC')
            self.assertEqual(s.episodes()[0]['focus'],T)
    def test_study_cutoff_rejects_future_selected_order(self):
        with tempfile.TemporaryDirectory() as d:
            s=StudyStore(d);e=event()
            with s.connect() as db:Store.order(db,e,'SYNTHETIC')
            self.assertIsNone(s.study('SYNTHETIC',cutoff=T)['event'])
            with self.assertRaises(ValueError):s.study('SYNTHETIC',e['id'],T)
            r=s.study('SYNTHETIC',e['id'],T+60)
            self.assertEqual(r['overview']['observed_orders'],1)
            self.assertIsNone(r['overview']['last_time'])

if __name__=='__main__':unittest.main()
