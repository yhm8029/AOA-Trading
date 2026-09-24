import unittest
from aoa.model import candle, clean_symbol, normalize_event, number, time_us, utc
from tests.fixtures import event, START


class ModelTests(unittest.TestCase):
    def test_time_units(self):
        expected=1622764800000000
        self.assertEqual(time_us('2021-06-04T00:00:00Z'),expected)
        self.assertEqual(time_us(1622764800),expected)
        self.assertEqual(time_us(1622764800000),expected)
        self.assertEqual(time_us(1622764800000000),expected)
        self.assertEqual(time_us('2021-06-04T09:00:00+09:00'),expected)
        self.assertEqual(time_us('2021-06-04 00:00:00.123456'),expected+123456)

    def test_time_invalid(self):
        for value in ('not-a-time','1900-01-01',-1):
            with self.assertRaises((ValueError,OverflowError)):
                time_us(value)

    def test_group_quantities_not_assumed_instantaneous(self):
        e,p=normalize_event(event(qty_before=5000000,qty=5000000,qty_after=20000000),'synthetic.csv',2)
        self.assertIn('GROUP_ENDPOINTS_INCLUDE_INTERLEAVED_ORDERS',e['warnings'])
        self.assertIn('GROUPED_ORDER_NOT_SINGLE_FILL',e['warnings'])
        self.assertEqual(e['qty_after'],20000000)
        self.assertEqual(p,100)

    def test_residual_is_not_full_close(self):
        e,_=normalize_event(event(event='CLOSE_SHORT',qty_before=1000000,qty_after=241),'synthetic.csv',2)
        self.assertEqual(e['event'],'NEAR_CLOSE_SHORT')
        self.assertEqual(e['raw_event'],'CLOSE_SHORT')

    def test_context_does_not_invent_tp(self):
        row=dict(ep_id=1,symbol='XBTUSD',role='Exit',direction='Long',orderid='synthetic',
          phase='first',event_time_assumed_utc='2021-06-04T01:00:00Z',execution_price=100,qty=100,
          pre_return_5m_pct='.12',post_next_full_15m_pct='7.2')
        e,p=normalize_event(row,'order_context.csv',2)
        self.assertEqual(e['event'],'REDUCE_LONG')
        self.assertEqual(e['reference_pair'],'BTCUSDT')
        self.assertNotIn('post_next_full_15m_pct',e['context'])
        self.assertEqual(e['context']['pre_return_5m_pct'],.12)
        self.assertEqual(p,50)

    def test_context_entry_without_size_is_unknown_increase(self):
        row=dict(ep_id=1,symbol='XBTUSD',role='Entry',direction='Long',orderid='test',phase='first',
            event_time_assumed_utc='2021-06-04T01:00:00Z',execution_price=100,qty=100)
        self.assertEqual(normalize_event(row,'context',2)[0]['event'],'INCREASE_LONG')

    def test_direction_required(self):
        with self.assertRaises(ValueError):
            normalize_event(event(direction=''),'synthetic.csv',2)

    def test_contract_not_assumed_btc(self):
        e,_=normalize_event(event(symbol='ETHUSD',reference_pair=''),'synthetic.csv',2)
        self.assertIsNone(e['reference_pair'])

    def test_first_and_average_prices_kept_separate(self):
        e,_=normalize_event(event(),'synthetic.csv',2)
        self.assertEqual(e['first_price'],103.2)
        self.assertEqual(e['group_vwap'],103.25)

    def test_known_minute_unit(self):
        c=candle(dict(reference_pair='BTCUSDT',minute_utc=START//60,open=1,high=3,low=.5,close=2,volume=0))
        self.assertEqual(c[1],START)
        self.assertEqual(c[-1],0)

    def test_bad_candle(self):
        for patch in ({'high':.1},{'low':5},{'close':0},{'volume':-1},{'open':'inf'}):
            row=dict(time=START,open=1,high=3,low=.5,close=2,volume=1)
            row.update(patch)
            with self.assertRaises(ValueError):
                candle(row)

    def test_strict_numbers_and_symbols(self):
        with self.assertRaises(ValueError):number('1.5',integer=True)
        with self.assertRaises(ValueError):number('inf')
        with self.assertRaises(ValueError):clean_symbol('../../BTC')
        self.assertIsNone(number(''))

if __name__=='__main__':unittest.main()
