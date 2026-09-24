import unittest
from aoa.model import adapt_order,merge_order,present_order,time_us,iso,aggregate,validate_bar


def order(**updates):
    row={'ep_id':'3086','symbol':'XBTUSD','role':'Entry','direction':'Short','orderid':'synthetic-order',
         'phase':'first','event_time_assumed_utc':'2021-06-04T12:32:13.123456+00:00','execution_price':'20000','qty':'5000000','reference_pair':'BTCUSDT'}
    row.update(updates)
    return row


class ModelTests(unittest.TestCase):
    def test_microseconds_and_timezone(self):
        a=time_us('2021-06-04 12:32:13.123456')
        self.assertEqual(a,time_us('2021-06-04T21:32:13.123456+09:00'))
        self.assertEqual(iso(a),'2021-06-04T12:32:13.123456+00:00')

    def test_first_and_last_are_one_order(self):
        first=adapt_order(order())
        last=adapt_order(order(phase='last',event_time_assumed_utc='2021-06-04T12:34:01+00:00',execution_price='20001'))
        result=merge_order(first,last)
        self.assertEqual(first['id'],last['id'])
        self.assertEqual(result['first_price'],20000)
        self.assertEqual(result['last_price'],20001)
        self.assertEqual(result['qty'],5000000)
        self.assertTrue(result['last_observed'])

    def test_last_received_first_is_corrected(self):
        last=adapt_order(order(phase='last',event_time_assumed_utc='2021-06-04T12:34:01+00:00',execution_price='20001'))
        first=adapt_order(order())
        result=merge_order(last,first)
        self.assertEqual(result['first_us'],first['first_us'])
        self.assertEqual(result['last_us'],last['last_us'])

    def test_overlap_is_not_fabricated_position_path(self):
        r=adapt_order(order(qty_before='5000000',qty_after='20000000'))
        out=present_order(r)
        self.assertIn('순간 보유량',out['warnings'][0])
        self.assertEqual(out['position_after'],20000000)

    def test_exit_is_not_automatically_take_profit(self):
        out=present_order(adapt_order(order(role='Exit')))
        self.assertEqual(out['action'],'REDUCE')
        self.assertIsNone(out['price_move_pct'])

    def test_short_cover_above_basis_is_loss_not_stop(self):
        out=present_order(adapt_order(order(role='Exit',execution_price='21000',avg_basis_before='20000')))
        self.assertEqual(out['action'],'LOSS_REDUCE')
        self.assertAlmostEqual(out['price_move_pct'],-5)

    def test_explicit_stop_wins(self):
        out=present_order(adapt_order(order(role='Exit',order_type='Stop',stop_trigger='20500')))
        self.assertEqual(out['action'],'STOP')
        self.assertEqual(out['stop_trigger'],20500)

    def test_legacy_label_kept_as_hypothesis(self):
        r={'episode_id':'42','event_time_utc':'2021-01-03 00:34:08.370328','event':'TACTICAL_CUT_SHORT','direction':'Short','qty':'5000','bitmex_vwap':'120','bitmex_first_fill':'119','qty_before':'10000','qty_after':'5000','avg_basis_before':'110','source_orderid':'test','classification_reason':'legacy heuristic','episode_net_pnl_btc':'-2'}
        out=present_order(adapt_order(r))
        self.assertEqual(out['action'],'LOSS_REDUCE')
        self.assertEqual(out['legacy_label'],'TACTICAL_CUT_SHORT')
        self.assertEqual(out['episode_pnl_btc'],-2)

    def test_post_features_not_loaded(self):
        out=adapt_order(order(pre_return_5m_pct='1.2',post_proxy_15m_return_pct='2.4'))
        self.assertEqual(out['context']['pre_return_5m_pct'],1.2)
        self.assertNotIn('post_proxy_15m_return_pct',out['context'])

    def test_unknown_role_rejected(self):
        with self.assertRaises(ValueError): adapt_order(order(role='Maybe'))

    def test_bad_numbers_rejected(self):
        for qty in ('nan','0','-5','4.2','inf'):
            with self.subTest(qty=qty),self.assertRaises(ValueError): adapt_order(order(qty=qty))

    def test_ohlc_validation(self):
        t=time_us('2021-06-04T12:00:00Z')//1000000
        self.assertEqual(validate_bar('BTCUSDT',t,100,102,98,101,0)[-1],0)
        for vals in ((100,99,98,101,1),(100,102,98,101,-1),(100,102,98,float('nan'),1)):
            with self.assertRaises(ValueError): validate_bar('BTCUSDT',t,*vals)
        with self.assertRaises(ValueError): validate_bar('BTCUSDT',t+1,100,102,98,101,1)

    def test_complete_clock_aligned_aggregate(self):
        t=time_us('2021-06-04T12:00:00Z')//1000000
        rows=[(t+i*60,100+i,103+i,98+i,101+i,10+i) for i in range(5)]
        out,missing=aggregate(rows,300,t,t+300)
        self.assertEqual(missing,0)
        self.assertEqual(out[0],{'time':t,'open':100,'high':107,'low':98,'close':105,'volume':60})

    def test_missing_minute_blanks_whole_higher_bar(self):
        t=time_us('2021-06-04T12:00:00Z')//1000000
        rows=[(t+i*60,100,102,98,101,10) for i in (0,1,3,4)]
        out,missing=aggregate(rows,300,t,t+300)
        self.assertEqual(out,[{'time':t}]); self.assertEqual(missing,1)

    def test_duplicate_minute_does_not_pass_completeness(self):
        t=time_us('2021-06-04T12:00:00Z')//1000000
        rows=[(t+i*60,100,102,98,101,10) for i in (0,1,1,3,4)]
        self.assertEqual(aggregate(rows,300,t,t+300)[1],1)

if __name__=='__main__': unittest.main()
